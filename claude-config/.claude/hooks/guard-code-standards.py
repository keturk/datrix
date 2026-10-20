"""PreToolUse hook (Write|Edit): the mechanical Code Standards, enforced on NEW code only.

CLAUDE.md, Code Standards, lists rules a parser can decide. Prose in context is paid on every turn
and ignored under pressure; a block is paid only when it fires. These are enforced here:

  * MOCKS AND FAKES IN TESTS. "Testing: real objects only, no `unittest.mock` /
    `SimpleNamespace` / fakes." In a test file: an import of `unittest.mock`, `mock` or
    `pytest_mock`, `from types import SimpleNamespace`, or a test function taking the `mocker`
    fixture.
  * SILENT EXCEPTION HANDLERS. "No `except: pass`." An `except` clause (bare or typed) whose body
    is only `pass` / `...`. A benign, narrowly-typed cleanup is `contextlib.suppress(SpecificError)`,
    which this does not match and which says what it ignores.
  * TODO COMMENTS. "No placeholders / TODOs." A `# TODO` / `FIXME` / `XXX` / `HACK` comment token
    (comment tokens only, so a string or a pattern list naming the word is never a hit).
  * MISSING TYPE HINTS. "Type hints on all fns." A function with no return annotation, or a
    parameter other than `self` / `cls` with no annotation.
  * `Any`. "No `Any` (exception: Pydantic `@model_validator(mode="before")` data param)." `Any` in a
    function's annotations or in an annotated assignment; a `mode="before"` model validator is exempt.
  * PRE-FORMATTED LOG MESSAGES. "Logging: %-style." A logger call (`LOG`/`log`/`logger`/`_logger`/
    `logging` and `self.` forms) whose message is an f-string, a `.format()` call, a `%` expression
    or a `+` concatenation instead of a format string with arguments.
  * SILENT FALLBACKS. "No silent fallbacks (`dict.get(key, None)`)." A `.get(key, None)` call.
  * FLATTENED ENTITIES. The cheat sheet's Entity Access rule, in generator sources only
    (`src/**/generators/`, `src/**/micro_generators/`): `app.all_entities()` (any `app`/`application`
    receiver), or one comprehension that iterates `app.services.values()` and then entities. The same
    shape is the ast-grep rule `flattened-entity-iteration` for audits.
  * COGNITIVE COMPLEXITY. "Cognitive complexity <= 15." A function whose cognitive complexity
    (the `cognitive_complexity` package, as `metrics/complexity.ps1` measures it) is above 15. Judged
    by function: a function already over the limit never blocks an edit; one the edit takes over it
    does. The package belongs to the shared venv, not to the interpreter running this hook, so the
    shared venv scores both sides of the edit (`python -m datrix_scripts.cognitive_scores`); skipped,
    and said so, when it cannot.
  * LITERAL-FACT TEST. In a package whose `tests/` carries the case runner `test_cases.py`, a literal
    fact about a stage result is a case row (`cases.ps1 new`), never a test function. A `test_*`
    function of the literal-fact shape -- every assertion compares one value with a string literal by
    `==`, `in` or `not in`, with no loop, comprehension or `pytest.raises` -- that the edit adds (by
    name) is refused. The shape is judged by
    `datrix_testing.conformance.assertion_inventory.literal_fact_tests`, the one definition the
    test-shape pin and the migration tool share; skipped, and said so, when that module is not
    importable.
  * MIGRATED TEST SHAPE. In the same packages, a fact a fixture line carries -- a diagnostic code of an
    analysis, the code a transpiler emits for one expression, a language server's answer at a `Position`,
    compared with a literal -- is an annotation on that line, never a test function. A `test_*` function
    of one of those shapes that the edit adds is refused, naming its carrier. The shapes are judged by
    `datrix_testing.conformance.assertion_inventory.migrated_shape_tests`, the definition the test-shape
    pins share; a test of a migrated shape is reported once (not again as a literal fact); skipped, and
    said so, when that module is not importable.
  * TABLE ROW TEST. In a package whose `tests/` carries the table runner `test_tables.py`, a fact
    about one row of a registered table (the builtin registry, a type map, an emit table, a DAL
    generator's file declarations) is proven by the runner's item for that row: adding the row is the
    whole change. A `test_*` function the edit adds (by name) that
    `python -m datrix_testing.tables.cli resolve` (the shared venv, which loads the package's
    registered tables) classifies as a per-row hand test -- its whole body looks a registered table's
    row up and compares it -- is refused, naming the rows and the items. Skipped, and said so, when the
    venv cannot resolve the module.
  * SCHEMA-SHAPED TEST. In a package whose `tests/` carries the model contract runner
    `test_model_contracts.py`, a required-field, default, bound, pattern, declared-constraint
    (`NonBlankStr`) or unknown-key fact of a model is proven by a derived runner item, never a test
    function. A `test_*` function the edit adds
    (by name) whose shape `datrix_testing.model_contracts.inventory` marks *raises* or *default*, and
    that `python -m datrix_testing.model_contracts.cli resolve` (the shared venv) resolves to schema
    facts, is refused, naming the model, the facts and the items that prove them. A test of a
    validator's rule, or one stating more than schema facts, is allowed. Skipped, and said so, when the
    inventory is not importable or the venv cannot resolve the module.
  * BODY WALKS. In a `datrix-codegen-*/src/` file, a generator reads the facts analysis records on a
    body (`datrix_common.datrix_model` `effects` / `usage` / `reads` / `resolution`) instead of
    walking it again. A walk-function, walk-method or `getattr` walk call the edit adds to a function
    not named in `scripts/config/no_body_walk_allowlist.json` is refused, naming the function
    and the call. The forms are judged by that gate's own matcher
    (`datrix_scripts.gates.repo_hygiene.no_body_walk_gate`, `function_walks`), read with the allowlist at
    run time; skipped when either cannot be loaded.
  * HISTORY COMMENTS. "Comments state what the code does now; history lives in git." A comment or
    docstring the edit adds that contains one of `_local_judge.HISTORY_WORDS` (`formerly`, `no longer`,
    `legacy`, ...) is put to the local second reader (`_local_judge.judge_comments`: a model already in
    memory, never a load). The words also describe current behaviour, so the edit is refused only when
    the reader answers "history" -- about the source code itself, not data or runtime state -- with a
    quote found verbatim in the added comment. No model, a timeout
    or an unreadable answer: allowed. `DATRIX_LOCAL_JUDGE=off` disables it.

SKIPPED CHECKS ARE REPORTED, NEVER SILENT. Five checks lean on something outside this interpreter:
cognitive complexity, table rows and schema-shaped tests on the shared venv (no interpreter, a module
missing from it, a failed or timed-out run), literal facts, migrated shapes and schema-shaped tests on
the shared test library read from the datrix-testing checkout (not importable). A check that cannot
run is skipped -- the edit is judged on the others, fail-open -- and the hook names every skipped
check with its reason and repair: a `systemMessage` on an allowed edit, a note under a refusal. A
rebuilt or partial venv therefore never disables a refusal without a word.

HOW IT DECIDES -- A DELTA, NEVER A SCAN. The file as it would exist after the edit is parsed and so
is the file as it exists now; a violation is reported only when the edit ADDS one (a multiset
difference over (kind, text)). A legacy `except: pass` elsewhere in the file never blocks an
unrelated edit, and removing one is never blocked. If either side does not parse, the hook cannot
compare and ALLOWS: this guard has no business refusing a file because its syntax is mid-edit.

SCOPE. `.py` files inside the framework repositories (`d:/datrix/datrix*`). Not generated output,
vendored or third-party trees, and not the harness's own hooks, whose fail-open handlers are
silent on purpose.

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

import ast
import collections
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Final, NoReturn, Protocol

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_log import SCRIPTS_LIB_DIR, add_scripts_lib_to_path  # noqa: E402
from _local_judge import CommentToken, comment_tokens, history_candidates, judge_comments, quoted_candidate  # noqa: E402

_FRAMEWORK_RE: Final = re.compile(r"^d:/datrix/datrix[^/]*/")
_EXEMPT_SEGMENTS: Final = (
    "/.venv/", "/.tmp/", "/.test-output/", "/.test_results/", "/node_modules/", "/site-packages/",
    "/generated/", "/.git/", "/claude-config/.claude/hooks/", "/.import_linter_cache/",
)
_MOCK_MODULES: Final = frozenset({"unittest.mock", "mock", "pytest_mock"})
_TODO_RE: Final = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_MAX_SHOWN: Final = 6
_MAX_COGNITIVE: Final = 15
_SELF_NAMES: Final = frozenset({"self", "cls", "mcs"})
_LOGGER_NAMES: Final = frozenset({"LOG", "log", "logger", "LOGGER", "_logger", "_log", "_LOG", "logging"})
_LOG_METHODS: Final = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical"})
_SHOWN_CALL_CHARS: Final = 90
_APP_RECEIVER_RE: Final = re.compile(r"^(self\.)?_?(app|application)$")
_SERVICES_ITER_RE: Final = re.compile(r"^(self\.)?_?(app|application)\.services\.values\(\)$")
# Generator sources, where an entity's owning service must survive iteration.
_GENERATOR_PATH_RE: Final = re.compile(r"/src/.*/(micro_)?generators/")
# A package's test tree, and the case runner whose presence makes a literal fact a case row.
_PACKAGE_TESTS_RE: Final = re.compile(r"^(d:/datrix/datrix[^/]*)/tests/")
_CASE_RUNNER: Final = "tests/test_cases.py"
# The model contract runner whose presence makes a schema fact a derived item.
_MODEL_CONTRACT_RUNNER: Final = "tests/test_model_contracts.py"
_TESTS_SEGMENT: Final = "/tests/"
# The shared venv's interpreter, which resolves a test to the model facts it restates.
_VENV_PYTHON: Final = "d:/datrix/.venv/Scripts/python.exe"
_RESOLVE_MODULE: Final = "datrix_testing.model_contracts.cli"
# The table runner whose presence makes a row fact a derived item, and the module resolving a test
# to the table rows it reads.
_TABLE_RUNNER: Final = "tests/test_tables.py"
_TABLE_RESOLVE_MODULE: Final = "datrix_testing.tables.cli"
_RESOLVE_TIMEOUT_SECONDS: Final = 180
# The dispositions of a test that restates only schema facts.
_SCHEMA_FACT_DISPOSITIONS: Final = frozenset({"covered", "uncovered"})
# The shared test library; the classifier's import chain is stdlib only.
_TESTING_SRC: Final = "d:/datrix/datrix-testing/src"
# The module the shared venv scores functions' cognitive complexity with, run from the scripts
# package's directory so `-m` finds it whatever the venv's own path holds.
_SCORER_MODULE: Final = "datrix_scripts.cognitive_scores"
_SCORE_TIMEOUT_SECONDS: Final = 30
# The overrides let the hook's test name a venv interpreter and a test-library root of its own; hook
# subprocesses inherit Claude Code's environment, not a shell the agent can export into, so neither is
# an escape hatch.
_VENV_PYTHON_OVERRIDE: Final = "DATRIX_CODESTD_VENV_PYTHON"
_TESTING_SRC_OVERRIDE: Final = "DATRIX_CODESTD_TESTING_SRC"
_VENV_MISSING: Final = (
    "The shared venv's interpreter {python} does not exist; create the venv and install the packages with "
    "scripts/common/venv.ps1 -Ensure -EnsurePackages."
)
_LIBRARY_MISSING: Final = (
    "The shared test library cannot be imported from {src}: {error}. The hook reads it from the "
    "datrix-testing checkout (its import chain is stdlib only); restore that checkout."
)
_COMPLEXITY_REMEDY: Final = "Measure the file with `metrics/complexity.ps1 -Files <file>` once the shared venv is repaired."
_SKIPPED_NOTE: Final = (
    "guard-code-standards: {count} check(s) did not run on this edit; the other Code Standards checks did.\n{checks}"
)
# A generator package's source tree, whose functions read recorded facts instead of walking bodies.
_CODEGEN_SOURCE_RE: Final = re.compile(r"^d:/datrix/(datrix-codegen-[^/]+/src/.+)$", re.IGNORECASE)
_SITE_SEPARATOR: Final = "::"

Violation = tuple[str, str]
FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
# A text's functions' cognitive complexity, keyed by the `def` line and column.
Scores = dict[tuple[int, int], int]
# The checks that could not run on an edit, each with why, gathered over both sides of the edit.
Skipped = dict[str, str]


class CheckUnavailable(Exception):
    """A check could not run on this edit: the shared venv or the test library is unavailable; the
    message says why and how to repair it."""


class _WalkCall(Protocol):
    form: str


BodyWalkMatcher = Callable[[str], Mapping[str, Sequence[_WalkCall]]]


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lower()


def _is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "/tests/" in path or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def _mock_import_violations(node: ast.Import) -> list[Violation]:
    return [("mock", f"import {alias.name}") for alias in node.names if alias.name in _MOCK_MODULES]


def _mock_from_import_violations(node: ast.ImportFrom) -> list[Violation]:
    module = node.module or ""
    if module in _MOCK_MODULES:
        return [("mock", f"from {module} import ...")]
    if module == "types" and any(alias.name == "SimpleNamespace" for alias in node.names):
        return [("mock", "from types import SimpleNamespace")]
    return []


def _mocker_fixture_violations(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Violation]:
    if any(arg.arg == "mocker" for arg in node.args.args + node.args.kwonlyargs):
        return [("mock", f"{node.name}(mocker)")]
    return []


def _mock_violations(tree: ast.AST) -> list[Violation]:
    found: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(_mock_import_violations(node))
        elif isinstance(node, ast.ImportFrom):
            found.extend(_mock_from_import_violations(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.extend(_mocker_fixture_violations(node))
    return found


def _silent_except_violations(tree: ast.AST) -> list[Violation]:
    found: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        silent = all(
            isinstance(stmt, ast.Pass)
            or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis)
            for stmt in node.body
        )
        if silent:
            found.append(("silent-except", f"except {ast.unparse(node.type) if node.type else '(bare)'}: pass"))
    return found


def _todo_violations(text: str) -> list[Violation]:
    found: list[Violation] = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT and _TODO_RE.search(token.string):
            found.append(("todo", token.string.strip()))
    return found


def _functions(tree: ast.AST) -> list[tuple[str, FunctionNode]]:
    """Every function with its qualified name (``Outer.method``, ``outer.inner``), in source order."""
    found: list[tuple[str, FunctionNode]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append((f"{prefix}{child.name}", child))
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def _params(node: FunctionNode) -> list[ast.arg]:
    args = node.args
    extra = [arg for arg in (args.vararg, args.kwarg) if arg is not None]
    return [*args.posonlyargs, *args.args, *args.kwonlyargs, *extra]


def _annotation_violations(functions: list[tuple[str, FunctionNode]]) -> list[Violation]:
    found: list[Violation] = []
    for name, node in functions:
        if node.returns is None:
            found.append(("type-hints", f"def {name}(...) has no return annotation"))
        found += [("type-hints", f"def {name}: parameter `{arg.arg}` has no annotation")
                  for arg in _params(node) if arg.annotation is None and arg.arg not in _SELF_NAMES]
    return found


def _mentions_any(annotation: ast.expr) -> bool:
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id == "Any":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "Any":
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"\bAny\b", node.value):
            return True
    return False


def _is_before_validator(node: FunctionNode) -> bool:
    """A Pydantic ``@model_validator(mode="before")``: the one place `Any` is allowed."""
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        callee = decorator.func
        named = (isinstance(callee, ast.Name) and callee.id == "model_validator") or (
            isinstance(callee, ast.Attribute) and callee.attr == "model_validator")
        if named and any(kw.arg == "mode" and isinstance(kw.value, ast.Constant) and kw.value.value == "before"
                         for kw in decorator.keywords):
            return True
    return False


def _any_violations(tree: ast.AST, functions: list[tuple[str, FunctionNode]]) -> list[Violation]:
    found: list[Violation] = []
    for name, node in functions:
        if _is_before_validator(node):
            continue
        annotations = [arg.annotation for arg in _params(node)] + [node.returns]
        found += [("any", f"def {name}: {ast.unparse(annotation)}")
                  for annotation in annotations if annotation is not None and _mentions_any(annotation)]
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and _mentions_any(node.annotation):
            found.append(("any", f"{ast.unparse(node.target)}: {ast.unparse(node.annotation)}"))
    return found


def _receiver_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _preformatted(message: ast.expr) -> bool:
    """A message built before the call: an f-string, a ``%``/``+`` expression, or ``.format()``."""
    if isinstance(message, ast.JoinedStr):
        return True
    if isinstance(message, ast.BinOp) and isinstance(message.op, (ast.Mod, ast.Add)):
        return True
    return isinstance(message, ast.Call) and isinstance(message.func, ast.Attribute) and message.func.attr == "format"


def _log_violations(tree: ast.AST) -> list[Violation]:
    found: list[Violation] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        method = node.func.attr
        if (method not in _LOG_METHODS and method != "log") or _receiver_name(node.func.value) not in _LOGGER_NAMES:
            continue
        index = 1 if method == "log" else 0
        if len(node.args) > index and _preformatted(node.args[index]):
            found.append(("log-format", ast.unparse(node)[:_SHOWN_CALL_CHARS]))
    return found


def _get_none_violations(tree: ast.AST) -> list[Violation]:
    return [("get-none", ast.unparse(node)[:_SHOWN_CALL_CHARS]) for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
            and len(node.args) == 2 and not node.keywords
            and isinstance(node.args[1], ast.Constant) and node.args[1].value is None]


def _app_receiver(node: ast.expr) -> bool:
    return bool(_APP_RECEIVER_RE.match(ast.unparse(node)))


def _flattened_entity_violations(tree: ast.AST) -> list[Violation]:
    """In a generator: the application's flattened entity set, or one comprehension over every
    service's entities (the cheat sheet's Entity Access rule; also the ast-grep rule
    ``flattened-entity-iteration``)."""
    found: list[Violation] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "all_entities" and _app_receiver(node.func.value)):
            found.append(("flattened-entities", ast.unparse(node)[:_SHOWN_CALL_CHARS]))
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            iters = [ast.unparse(generator.iter) for generator in node.generators]
            over_services = [i for i, text in enumerate(iters) if _SERVICES_ITER_RE.match(text)]
            if over_services and any("entities" in text for text in iters[over_services[0] + 1:]):
                found.append(("flattened-entities", ast.unparse(node)[:_SHOWN_CALL_CHARS]))
    return found


def _run_venv_module(arguments: list[str], text: str, timeout: int, cwd: str | None = None) -> str:
    """What `<shared venv python> -m <arguments>` prints when fed ``text``.

    Raises CheckUnavailable when the venv cannot run it: no interpreter, a run that does not finish,
    or a nonzero exit (its last line of output says why).
    """
    python = os.environ.get(_VENV_PYTHON_OVERRIDE) or _VENV_PYTHON
    command = f"`{python} -m {' '.join(arguments)}`"
    if not os.path.isfile(python):
        raise CheckUnavailable(_VENV_MISSING.format(python=python))
    try:
        completed = subprocess.run(
            [python, "-m", *arguments], input=text, cwd=cwd,
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CheckUnavailable(f"{command} did not finish: {exc}") from exc
    if completed.returncode != 0:
        output = (completed.stderr.strip() or completed.stdout.strip()).splitlines()
        raise CheckUnavailable(f"{command} exited {completed.returncode}: "
                               f"{output[-1] if output else 'no output'}")
    return completed.stdout


def _cognitive_scores(texts: list[str]) -> list[Scores]:
    """Each text's function scores, from the shared venv in one run.

    Raises CheckUnavailable when the venv cannot score them.
    """
    stdout = _run_venv_module([_SCORER_MODULE], json.dumps(texts), _SCORE_TIMEOUT_SECONDS, cwd=SCRIPTS_LIB_DIR)
    try:
        rows = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CheckUnavailable(f"`-m {_SCORER_MODULE}` printed no JSON: {exc}") from exc
    return [{(line, column): score for line, column, score in per_text} for per_text in rows]


def _complexity_violations(functions: list[tuple[str, FunctionNode]], scores: Scores) -> list[Violation]:
    """Functions over the cognitive-complexity limit, keyed by name only so a function already over
    it is not "added" again by an edit that changes its score. A function the scorer could not read
    has no score; the metrics script reports it."""
    found: list[Violation] = []
    for name, node in functions:
        position = (node.lineno, node.col_offset)
        if position in scores and scores[position] > _MAX_COGNITIVE:
            found.append(("complexity", f"def {name} is above {_MAX_COGNITIVE}"))
    return found


def _testing_src() -> str:
    """The shared test library's source root, put on the import path."""
    src = os.environ.get(_TESTING_SRC_OVERRIDE) or _TESTING_SRC
    if src not in sys.path:
        sys.path.insert(0, src)
    return src


def _literal_fact_classifier() -> Callable[[ast.Module], Iterable[FunctionNode]]:
    """The shared literal-fact classifier. Raises CheckUnavailable when the test library is not importable."""
    src = _testing_src()
    try:
        from datrix_testing.conformance.assertion_inventory import literal_fact_tests
    except ImportError as exc:
        raise CheckUnavailable(_LIBRARY_MISSING.format(src=src, error=exc)) from exc
    return literal_fact_tests


def carries_cases(path: str) -> bool:
    """Whether the package holding the test at ``path`` carries the case runner."""
    match = _PACKAGE_TESTS_RE.match(path)
    return bool(match) and os.path.isfile(f"{match.group(1)}/{_CASE_RUNNER}")


def _migrated_shape_classifier() -> Callable[[ast.Module], Iterable[tuple[FunctionNode, str]]]:
    """The shared migrated-shape classifier. Raises CheckUnavailable when the test library is not importable."""
    src = _testing_src()
    try:
        from datrix_testing.conformance.assertion_inventory import migrated_shape_tests
    except ImportError as exc:
        raise CheckUnavailable(_LIBRARY_MISSING.format(src=src, error=exc)) from exc
    return migrated_shape_tests


def carries_model_contracts(path: str) -> bool:
    """Whether the package holding the test at ``path`` carries the model contract runner."""
    match = _PACKAGE_TESTS_RE.match(path)
    return bool(match) and os.path.isfile(f"{match.group(1)}/{_MODEL_CONTRACT_RUNNER}")


def _schema_shaped_names(text: str) -> set[str] | None:
    """The qualified names of the schema-shaped tests of ``text``; None when it does not parse.

    Raises CheckUnavailable when the test library's inventory is not importable.
    """
    src = _testing_src()
    try:
        from datrix_testing.model_contracts.inventory import schema_shaped_tests
    except ImportError as exc:
        raise CheckUnavailable(_LIBRARY_MISSING.format(src=src, error=exc)) from exc
    try:
        return {test.function for test in schema_shaped_tests(ast.parse(text))}
    except (SyntaxError, ValueError):
        return None


def _resolved_records(module: str, path: str, text: str) -> list[dict[str, object]]:
    """The JSON records `<module> resolve` prints for the test module ``text`` at ``path``.

    Raises CheckUnavailable when the shared venv cannot resolve it.
    """
    match = _PACKAGE_TESTS_RE.match(path)
    if not match:
        return []
    test_module = path.split(_TESTS_SEGMENT, 1)[1]
    stdout = _run_venv_module([module, "resolve", match.group(1), test_module], text, _RESOLVE_TIMEOUT_SECONDS)
    records: list[dict[str, object]] = []
    for line in stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _resolved_schema_facts(path: str, text: str, names: set[str]) -> list[Violation]:
    """The added tests among ``names`` the shared venv resolves to schema facts.

    Raises CheckUnavailable when the shared venv cannot resolve them.
    """
    found: list[Violation] = []
    for record in _resolved_records(_RESOLVE_MODULE, path, text):
        if record["function"] in names and record["disposition"] in _SCHEMA_FACT_DISPOSITIONS:
            proven = ", ".join(record["items"]) if record["disposition"] == "covered" else "no item yet: add a fixture"
            found.append(("schema-shaped", f"def {record['function']} restates {record['model']} "
                                           f"[{', '.join(record['facts'])}] (proven by: {proven})"))
    return found


def _schema_shaped_violations(path: str, before: str | None, after: str, skipped: Skipped) -> list[Violation]:
    """The schema-shaped tests this edit adds that restate model facts the runner proves; a check that
    cannot run is recorded in ``skipped``."""
    try:
        after_names = _schema_shaped_names(after)
        before_names = set() if before is None else _schema_shaped_names(before)
        if after_names is None or before_names is None:
            return []
        added = after_names - before_names
        return _resolved_schema_facts(path, after, added) if added else []
    except CheckUnavailable as exc:
        skipped["schema-shaped"] = str(exc)
        return []


def carries_tables(path: str) -> bool:
    """Whether the package holding the test at ``path`` carries the table runner."""
    match = _PACKAGE_TESTS_RE.match(path)
    return bool(match) and os.path.isfile(f"{match.group(1)}/{_TABLE_RUNNER}")


def _test_names(text: str | None) -> set[str] | None:
    """The qualified names of the test functions ``text`` defines; None when it does not parse."""
    if text is None:
        return set()
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    names: set[str] = set()

    def visit(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                names.add(f"{prefix}{node.name}")
            elif isinstance(node, ast.ClassDef):
                visit(node.body, f"{prefix}{node.name}.")

    visit(tree.body, "")
    return names


def _table_row_violations(path: str, before: str | None, after: str, skipped: Skipped) -> list[Violation]:
    """The per-row hand tests this edit adds (by name) over the package's registered tables; a check
    that cannot run is recorded in ``skipped``."""
    before_names = _test_names(before)
    after_names = _test_names(after)
    if before_names is None or after_names is None or not (after_names - before_names):
        return []
    try:
        records = _resolved_records(_TABLE_RESOLVE_MODULE, path, after)
    except CheckUnavailable as exc:
        skipped["table-row"] = str(exc)
        return []
    found: list[Violation] = []
    for record in records:
        if record["function"] in before_names:
            continue
        rows = record["rows"] if isinstance(record["rows"], list) else []
        items = ", ".join(f"test_table[{row}]" for row in rows) or "no item yet: the row is in no registered table"
        found.append(("table-row", f"def {record['function']} reads {', '.join(record['lookups'])} "
                                   f"({record['disposition']}; proven by: {items})"))
    return found


def _case_violations(tree: ast.Module, skipped: Skipped) -> list[Violation]:
    """Tests whose fact a case carries: a migrated shape (its fixture line's annotation), else a
    literal fact (a case row). A test of a migrated shape is reported once, with its carrier. A
    classifier that cannot be imported is recorded in ``skipped``."""
    found: list[Violation] = []
    migrated: set[str] = set()
    try:
        shapes = _migrated_shape_classifier()
    except CheckUnavailable as exc:
        skipped["migrated-shape"] = str(exc)
    else:
        for function, shape in shapes(tree):
            migrated.add(function.name)
            found.append(("migrated-shape", f"def {function.name} ({shape})"))
    try:
        literal = _literal_fact_classifier()
    except CheckUnavailable as exc:
        skipped["literal-fact"] = str(exc)
    else:
        found += [("literal-fact", f"def {f.name}") for f in literal(tree) if f.name not in migrated]
    return found


def _body_walk_rule() -> tuple[BodyWalkMatcher, frozenset[str]] | None:
    """The no-body-walk gate's matcher and its allowlisted sites (lowercased); None when either
    cannot be loaded."""
    add_scripts_lib_to_path()
    try:
        from datrix_scripts.gates.repo_hygiene.no_body_walk_gate import AllowlistError, function_walks, load_allowlist
    except ImportError:
        return None
    try:
        allowlist = load_allowlist()
    except (AllowlistError, OSError):
        return None
    return function_walks, frozenset(site.lower() for site in allowlist)


def _unlisted_body_walks(relative: str, text: str, matcher: BodyWalkMatcher,
                         allowed: frozenset[str]) -> collections.Counter[Violation]:
    """The flagged calls of ``text`` in functions the allowlist does not name, keyed by site and form."""
    found: collections.Counter[Violation] = collections.Counter()
    for unit, calls in matcher(text).items():
        site = f"{relative}{_SITE_SEPARATOR}{unit}"
        if site.lower() not in allowed:
            found.update(("body-walk", f"{site} calls {call.form}") for call in calls)
    return found


def _body_walk_violations(raw_path: str, before: str | None, after: str) -> collections.Counter[Violation]:
    """The body-walk calls this edit adds to unlisted functions of a generator package's source."""
    match = _CODEGEN_SOURCE_RE.match(raw_path.replace("\\", "/"))
    if not match:
        return collections.Counter()
    rule = _body_walk_rule()
    if rule is None:
        return collections.Counter()
    matcher, allowed = rule
    try:
        after_found = _unlisted_body_walks(match.group(1), after, matcher, allowed)
        before_found = (collections.Counter() if before is None
                        else _unlisted_body_walks(match.group(1), before, matcher, allowed))
    except (SyntaxError, ValueError):
        return collections.Counter()
    return after_found - before_found


def _added_comments(before: str | None, after: str) -> list[CommentToken] | None:
    """The comments and docstrings ``after`` holds that ``before`` does not (a multiset difference by
    text), or None when either side does not parse."""
    try:
        remaining = collections.Counter(t.text for t in ([] if before is None else comment_tokens(before)))
        after_tokens = comment_tokens(after)
    except (SyntaxError, ValueError, tokenize.TokenError):
        return None
    added: list[CommentToken] = []
    for token in after_tokens:
        if remaining[token.text]:
            remaining[token.text] -= 1
        else:
            added.append(token)
    return added


def _history_comment_violations(before: str | None, after: str) -> list[Violation]:
    candidates = history_candidates(_added_comments(before, after) or [])
    judgement = judge_comments(candidates, after)
    if not judgement.flagged:
        return []
    token = quoted_candidate(candidates, judgement.quote)
    where = f"line {token.line} ({token.kind})" if token else "an added comment"
    return [("history-comment", f"{where}: \"{judgement.quote.strip()}\"")]


def _violations(
    text: str, scores: Scores, is_test: bool, skipped: Skipped, is_generator: bool = False, cases: bool = False
) -> collections.Counter[Violation] | None:
    """The violations in ``text``, or None when it cannot be parsed (so the caller cannot judge)."""
    try:
        tree = ast.parse(text)
        functions = _functions(tree)
        found = _silent_except_violations(tree) + _todo_violations(text)
        found += _annotation_violations(functions) + _any_violations(tree, functions)
        found += _log_violations(tree) + _get_none_violations(tree) + _complexity_violations(functions, scores)
        if is_generator:
            found += _flattened_entity_violations(tree)
        if is_test:
            found += _mock_violations(tree)
        if cases:
            found += _case_violations(tree, skipped)
    except (SyntaxError, ValueError, tokenize.TokenError, IndentationError):
        return None
    return collections.Counter(found)


def _after_text(tool: str, tool_input: dict[str, object], before: str | None) -> str | None:
    if tool == "Write":
        return str(tool_input.get("content", ""))
    if before is None:
        return None
    old = str(tool_input.get("old_string", ""))
    new = str(tool_input.get("new_string", ""))
    if not old or old not in before:
        return None
    return before.replace(old, new) if tool_input.get("replace_all") else before.replace(old, new, 1)


_REMEDY: Final = {
    "mock": (
        "CLAUDE.md, Code Standards: 'Testing: real objects only, no `unittest.mock`/`SimpleNamespace`/fakes.' "
        "Build the real thing: a real AST from `datrix_testing` factories or a `.dtrx` snippet through the "
        "parser, a real object of the class under test, a real temporary directory or loopback server. If "
        "the real object is hard to build, that is the missing test helper to add in `datrix-testing`."
    ),
    "silent-except": (
        "CLAUDE.md, Anti-patterns: 'No `except: pass`.' A handler that swallows an error turns a failure "
        "into silence. Catch the narrowest exception you can name and handle it (return the documented "
        "value, raise a clearer error with what was expected and valid options), log it with "
        "`logging.getLogger(__name__)` if it is genuinely survivable, or let it propagate. For a benign, "
        "narrowly-typed cleanup (`FileNotFoundError` on a delete) use `contextlib.suppress(FileNotFoundError)`, "
        "which says what is ignored."
    ),
    "todo": (
        "CLAUDE.md, Anti-patterns: 'No placeholders/TODOs.' A TODO is a promise nobody keeps: there is no "
        "later. Do the work now, or, if it is genuinely a separate defect, file it (a tracked task, or a "
        "findings file under `d:\\datrix\\reports\\finding\\`, execution-contract-reporting.md section 5A) "
        "and leave the code without the comment."
    ),
    "type-hints": (
        "CLAUDE.md, Code Standards: 'Type hints on all fns.' Annotate every parameter (except `self`/`cls`) "
        "and the return type, `-> None` included. The tests of the code you changed are the type gate; "
        "no type-checker runs."
    ),
    "any": (
        "CLAUDE.md, Code Standards: 'No `Any`' (the one exception is the data parameter of a Pydantic "
        "`@model_validator(mode=\"before\")`). Name the real type: a union, a Protocol, a TypedDict, "
        "`object` plus a narrowing `isinstance`, or a generic parameter."
    ),
    "log-format": (
        "CLAUDE.md, Code Standards: 'Logging: `logging.getLogger(__name__)`, %-style.' Pass a format string "
        "and its arguments, e.g. `LOG.info(\"Wrote %s (%d files)\", path, count)`, never an f-string, "
        "`.format()`, `%` or `+`: the message is built only when the record is emitted, and handlers see "
        "the arguments."
    ),
    "get-none": (
        "CLAUDE.md, Anti-patterns: 'No silent fallbacks (`dict.get(key, None)`).' Decide what a missing key "
        "means: index it (`d[key]`) when it must exist, or check `if key not in d:` and raise an error that "
        "says what was expected and what was found."
    ),
    "flattened-entities": (
        "Architecture cheat sheet, Entity Access: 'Entities are block-scoped. Always iterate per-service, "
        "per-block; never flatten across services.' A generator walks `for service in app.services.values()` "
        "-> `service.rdbms_blocks` -> `block.entities` (or `service.all_entities()`), so every artifact it "
        "emits keeps its owning service."
    ),
    "complexity": (
        "CLAUDE.md, Code Standards: 'Cognitive complexity <=15; max 3 nesting; early returns.' Split the "
        "function: guard clauses and early returns for the edge cases, and a named helper per branch or "
        "loop body. Only a function this edit takes over the limit is refused."
    ),
    "literal-fact": (
        "CLAUDE.md, Code Standards: in a package whose tests/ carries test_cases.py, a literal fact about a "
        "stage result is a case row, never a test function (unit-test-guidelines.md section 4, 'Decision "
        "facts as cases'). Add it with `datrix/scripts/test/cases.ps1 new <package> <area> -Id <area>.<slug> "
        "-Tags <tags> -Input <named input> -Stage <stage> -Observer <kind> -Selector \"{...}\" -Expectation "
        "<value> -Reason \"<the decision it protects>\"`. The observer kind follows the fact: a `not in` is "
        "an `absent` case (no expectation), a field of a file's recorded render context a `context` case, a "
        "parsed unit of a generated file a `surface` case, a file set a `paths` case, a diagnostic an "
        "`analyze`-stage `diagnostics` case. A fact that is not one literal comparison -- an invariant over "
        "a set, an exception path, an algorithm's edge cases -- stays a code test."
    ),
    "migrated-shape": (
        "CLAUDE.md, Code Standards: in a package whose tests/ carries test_cases.py, a diagnostic, "
        "transpiled-expression, parse or language-server fact is carried by the fixture line that provokes "
        "it, never by a test function (unit-test-guidelines.md section 4, 'Fixture-carried facts'): "
        "`// @expect <CODE>[.<variant>]` or `// @expect-none` on the line a diagnostic fires at, "
        "`// @emits <expression>` on a function whose body is one return, a `$0` cursor with `// @hover`, "
        "`// @complete` or `// @definition` for a language-server answer. Until the fixture carries it, the "
        "same fact is a case row (`cases.ps1 new`, an `analyze`/`diagnostics` or `transpile`/`transpiled` "
        "case). A fact that is not one literal comparison stays a code test."
    ),
    "schema-shaped": (
        "CLAUDE.md, Code Standards: a required-field, default, bound, pattern or unknown-key fact about a "
        "model is never a test function: the package's model contract runner (tests/test_model_contracts.py) "
        "derives it from the model and proves it on a committed .dcfg fixture sample "
        "(unit-test-guidelines.md, 'Model facts are derived'). The fact is proven already, or will be once a "
        "committed fixture reaches the model: write that fixture (`datrix/scripts/test/model-contracts.ps1 "
        "facts <package>` lists the models no fixture reaches). A validator's rule stays a code test that "
        "asserts the error's location and type after the `pytest.raises` block."
    ),
    "table-row": (
        "CLAUDE.md, Code Standards: a fact about one row of a registered table is proven by the table runner "
        "(tests/test_tables.py), never by a test function (unit-test-guidelines.md, 'Table rows'): every row "
        "of the table is one item, test_table[<table>::<row id>], that proves the row's property through the "
        "real code path. Adding the row is the whole change; run it with `test.ps1 <package> -Tag <table "
        "tag>` (`datrix/scripts/test/tables.ps1 rows <package>` lists the items). A specific value a design "
        "decided for a row is a case row (`cases.ps1 new`) or the table's own reviewed diff. A row the item "
        "fails is a row defect or a code-path defect: fix the row or the code."
    ),
    "body-walk": (
        "A generator reads the facts analysis records on a body instead of walking it again: "
        "`datrix_common.datrix_model.effects` / `usage` / `reads` / `resolution` (what a body calls, "
        "reads, writes and resolves). The walks that remain are a closed list, "
        "`datrix/scripts/config/no_body_walk_allowlist.json`, each with one of the "
        "categories render-traversal, emission-syntax, emission-decision, literal-content or "
        "no-facts-boundary; adding a function to it needs Jon's approval, and a genuinely new category "
        "is a design change that needs it too. `gates/repo-hygiene/no-body-walk-gate.ps1` holds the "
        "same rule over every generator package."
    ),
    "history-comment": (
        "Code quality standards, Comments: a comment or docstring states what the code does now; git holds "
        "the history. The local second reader read the quoted words as change history (what the code used "
        "to do, where it came from, what it replaced, which phase or migration removed something). Rewrite "
        "the comment to state what the code does now, or drop it if nothing remains once the history is "
        "gone. A phase, design or task reference goes too."
    ),
}


def _skipped_note(skipped: Skipped) -> str:
    """The note naming every check that could not run on this edit, with why; empty when all ran."""
    if not skipped:
        return ""
    checks = "\n".join(f"  - {check}: {reason}" for check, reason in sorted(skipped.items()))
    return _SKIPPED_NOTE.format(count=len(skipped), checks=checks)


def _allow(skipped: Skipped) -> NoReturn:
    """Allow the edit, telling Jon about every check that could not judge it."""
    note = _skipped_note(skipped)
    if note:
        print(json.dumps({"systemMessage": note}))
    sys.exit(0)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    raw_path = str(tool_input.get("file_path", ""))
    if tool not in ("Write", "Edit") or not raw_path.lower().endswith(".py"):
        sys.exit(0)

    path = _normalize(raw_path)
    if not _FRAMEWORK_RE.match(path) or any(seg in path for seg in _EXEMPT_SEGMENTS):
        sys.exit(0)

    before = _read(raw_path)
    after = _after_text(tool, tool_input, before)
    if after is None:
        sys.exit(0)

    texts = [after] if before is None else [after, before]
    skipped: Skipped = {}
    try:
        scores = _cognitive_scores(texts)
    except CheckUnavailable as exc:
        scores = [{} for _ in texts]
        skipped["cognitive-complexity"] = f"{exc} {_COMPLEXITY_REMEDY}"

    is_test = _is_test_file(path)
    is_generator = not is_test and bool(_GENERATOR_PATH_RE.search(path))
    cases = is_test and carries_cases(path)
    after_found = _violations(after, scores[0], is_test, skipped, is_generator, cases)
    before_found = (collections.Counter() if before is None
                    else _violations(before, scores[1], is_test, skipped, is_generator, cases))
    if after_found is None or before_found is None:
        _allow(skipped)

    added = after_found - before_found
    added.update(_body_walk_violations(raw_path, before, after))
    if is_test and carries_model_contracts(path):
        added.update(_schema_shaped_violations(path, before, after, skipped))
    if is_test and carries_tables(path):
        added.update(_table_row_violations(path, before, after, skipped))
    added.update(_history_comment_violations(before, after))
    if not added:
        _allow(skipped)

    kinds = sorted({kind for kind, _ in added})
    lines = [f"  - [{kind}] {text}" for (kind, text), count in sorted(added.items())
             for _ in range(count)][:_MAX_SHOWN]
    sys.stderr.write(
        f"BLOCKED: this edit to `{raw_path}` adds code the Code Standards forbid:\n"
        + "\n".join(lines)
        + "\n\n"
        + "\n\n".join(_REMEDY[kind] for kind in kinds)
        + "\n\nOnly what this edit ADDS is judged; existing code in the file is never a reason to refuse an edit."
        + (f"\n\n{_skipped_note(skipped)}" if skipped else "")
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
