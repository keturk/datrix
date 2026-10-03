"""PreToolUse hook (Write|Edit): the mechanical Code Standards, enforced on NEW code only.

CLAUDE.md, Code Standards, lists rules a parser can decide. Prose in context is paid on every turn
and ignored under pressure; a block is paid only when it fires. Three are enforced here:

  * MOCKS AND FAKES IN TESTS. "Testing: real objects only, no `unittest.mock` /
    `SimpleNamespace` / fakes." In a test file: an import of `unittest.mock`, `mock` or
    `pytest_mock`, `from types import SimpleNamespace`, or a test function taking the `mocker`
    fixture.
  * SILENT EXCEPTION HANDLERS. "No `except: pass`." An `except` clause (bare or typed) whose body
    is only `pass` / `...`. A benign, narrowly-typed cleanup is `contextlib.suppress(SpecificError)`,
    which this does not match and which says what it ignores.
  * TODO COMMENTS. "No placeholders / TODOs." A `# TODO` / `FIXME` / `XXX` / `HACK` comment token
    (comment tokens only, so a string or a pattern list naming the word is never a hit).

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

Violation = tuple[str, str]


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


def _violations(text: str, is_test: bool) -> collections.Counter[Violation] | None:
    """The violations in ``text``, or None when it cannot be parsed (so the caller cannot judge)."""
    try:
        tree = ast.parse(text)
        found = _silent_except_violations(tree) + _todo_violations(text)
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
    after_found = _violations(after, is_test)
    before_found = collections.Counter() if before is None else _violations(before, is_test)
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
