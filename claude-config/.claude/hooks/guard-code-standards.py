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
    does. Skipped when the package is not importable.

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
import re
import sys
import tokenize
from typing import Final

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

Violation = tuple[str, str]
FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


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


def _mock_violations(tree: ast.AST) -> list[Violation]:
    found: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _MOCK_MODULES:
                    found.append(("mock", f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in _MOCK_MODULES:
                found.append(("mock", f"from {module} import ..."))
            elif module == "types" and any(alias.name == "SimpleNamespace" for alias in node.names):
                found.append(("mock", "from types import SimpleNamespace"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(arg.arg == "mocker" for arg in node.args.args + node.args.kwonlyargs):
                found.append(("mock", f"{node.name}(mocker)"))
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


def _complexity_violations(functions: list[tuple[str, FunctionNode]]) -> list[Violation]:
    """Functions over the cognitive-complexity limit, keyed by name only so a function already over
    it is not "added" again by an edit that changes its score."""
    try:
        from cognitive_complexity.api import get_cognitive_complexity
    except ImportError:
        return []
    found: list[Violation] = []
    for name, node in functions:
        try:
            score = get_cognitive_complexity(node)
        except (RecursionError, ValueError, TypeError, AttributeError):
            continue  # the scorer cannot read this construct; the metrics script reports it
        if score > _MAX_COGNITIVE:
            found.append(("complexity", f"def {name} is above {_MAX_COGNITIVE}"))
    return found


def _violations(text: str, is_test: bool, is_generator: bool = False) -> collections.Counter[Violation] | None:
    """The violations in ``text``, or None when it cannot be parsed (so the caller cannot judge)."""
    try:
        tree = ast.parse(text)
        functions = _functions(tree)
        found = _silent_except_violations(tree) + _todo_violations(text)
        found += _annotation_violations(functions) + _any_violations(tree, functions)
        found += _log_violations(tree) + _get_none_violations(tree) + _complexity_violations(functions)
        if is_generator:
            found += _flattened_entity_violations(tree)
        if is_test:
            found += _mock_violations(tree)
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
}


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

    is_test = _is_test_file(path)
    is_generator = not is_test and bool(_GENERATOR_PATH_RE.search(path))
    after_found = _violations(after, is_test, is_generator)
    before_found = collections.Counter() if before is None else _violations(before, is_test, is_generator)
    if after_found is None or before_found is None:
        sys.exit(0)

    added = after_found - before_found
    if not added:
        sys.exit(0)

    kinds = sorted({kind for kind, _ in added})
    lines = [f"  - [{kind}] {text}" for (kind, text), count in sorted(added.items())
             for _ in range(count)][:_MAX_SHOWN]
    sys.stderr.write(
        f"BLOCKED: this edit to `{raw_path}` adds code the Code Standards forbid:\n"
        + "\n".join(lines)
        + "\n\n"
        + "\n\n".join(_REMEDY[kind] for kind in kinds)
        + "\n\nOnly what this edit ADDS is judged; existing code in the file is never a reason to refuse an edit."
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
