#!/usr/bin/env python3
"""First-pass review of pending changes, before they are committed.

Reviews only the lines a pending change ADDS to a Python file, in every workspace
repository with uncommitted changes, in two layers:

DEFINITE
    Checks read from the syntax tree of the file as it now stands, reported only where
    the flagged line is an added one: a silent ``.get(key, None)`` fallback, a bare
    ``except:``, an ``except ...: pass``, a TODO/FIXME/XXX/HACK comment, a function
    missing a return or parameter annotation, and a placeholder body (only ``pass``,
    ``...``, a docstring or ``raise NotImplementedError``, outside Protocol/ABC classes
    and ``@abstractmethod``/``@overload`` declarations). Each is a CLAUDE.md
    anti-pattern with no legitimate spelling in framework code, so these alone decide
    the exit code. Runs entirely on this machine.

ADVISORY (opt-in: ``--model-review``)
    A local model (``datrix_scripts.local_llm``) reviews the added hunks of non-test files
    against rules that need judgement: silent fallbacks, weak error messages, secrets in
    logs, string-built commands, fail-open guards, broad excepts. A finding is kept only
    at high confidence, on an added line, and quoting code that line contains. Measured
    on 17.9k added lines with qwen3.6-35b, 44 findings survived those filters and nearly
    all were false positives (parameterized SQL read as injection, Protocol stubs read as
    placeholders, re-raising excepts read as swallowing), in 165 s -- so it is off by
    default and never decides the exit code. Code sent for review crosses the local
    network over plain HTTP, as every local-model script's input does.

Exit codes: 0 no definite findings, 1 definite findings, 2 the review could not run.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import subprocess
import sys
import tokenize
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from datrix_scripts.code_index.sources import discover_repos
from datrix_scripts.local_llm import (
    ChatRequest,
    LocalHost,
    LocalLlmPool,
    LocalLlmUnavailable,
    add_local_llm_arguments,
    local_llm_settings,
)
from datrix_scripts.venv import get_datrix_root

EXIT_CLEAN = 0
EXIT_DEFINITE_FINDINGS = 1
EXIT_CANNOT_RUN = 2

GIT_TIMEOUT_SECONDS = 120
PYTHON_PATHSPEC = "*.py"

RULE_GET_NONE = "get-none"
RULE_BARE_EXCEPT = "bare-except"
RULE_EXCEPT_PASS = "except-pass"
RULE_TODO = "todo-comment"
RULE_UNTYPED_DEF = "untyped-def"
RULE_PLACEHOLDER = "placeholder"
RULE_SYNTAX = "syntax-error"

DEFINITE_EXPLANATIONS = {
    RULE_GET_NONE: "silent fallback: .get(key, None) turns a missing key into None; index it and let it "
                   "raise, or raise a named error listing the valid keys",
    RULE_BARE_EXCEPT: "bare except: catches everything, including KeyboardInterrupt; name the exceptions",
    RULE_EXCEPT_PASS: "swallowed exception: an except whose body is only pass/...; handle it or let it raise",
    RULE_TODO: "placeholder comment: finish the work now; there is no later",
    RULE_UNTYPED_DEF: "missing type hints: every parameter and the return need an annotation",
    RULE_PLACEHOLDER: "placeholder body: only pass, ..., a docstring, or raise NotImplementedError; write the "
                      "real logic (Protocol, ABC, @abstractmethod and @overload declarations are exempt)",
    RULE_SYNTAX: "the file does not parse",
}

_TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_RECEIVER_NAMES = frozenset({"self", "cls"})
# A body of nothing is a declaration, not a placeholder, in these places.
_DECLARATION_DECORATORS = frozenset({"abstractmethod", "overload", "abstractproperty"})
_INTERFACE_BASES = frozenset({"Protocol", "ABC"})
_NOT_IMPLEMENTED = "NotImplementedError"

# Rules the model judges, with the wording it is shown. Ids double as the JSON enum.
# Deliberately absent: "magic value", "T | None error return" and "fake in a test". Measured
# on 17.8k added lines, a 35B model flagged every optional return and every literal, drowning
# the real findings; mocks in tests are already a hard ruff ban (TID251).
ADVISORY_RULES = {
    "silent-fallback": "a missing or invalid value silently replaced by a default instead of raising",
    "always-true-check": "a validator or guard that cannot fail -- it accepts every input",
    "weak-error-message": "a raised error whose message does not say what went wrong, what was expected, "
                          "and how to fix it",
    "secret-in-log": "a secret, token, credential or personal data written to a log, error or output",
    "string-built-command": "SQL, a shell command, a path or markup assembled from outside input by "
                            "string concatenation or formatting",
    "fail-open": "a guard or check that allows when it cannot evaluate its input",
    "broad-except": "an except that catches Exception or wider and continues as if nothing failed",
}

# Model findings are kept only at this confidence, and only when their quote is found
# verbatim in the line they name: both measured as the difference between a reviewable
# list and a list nobody should read.
KEPT_CONFIDENCE = "high"
MAX_QUOTE_CHARS = 160
MAX_EXPLANATION_CHARS = 240
_TEST_PATH_RE = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$")

MODEL_TEMPERATURE = 0.0
MODEL_MAX_TOKENS = 1200
CONTEXT_LINES = 3
DEFAULT_MAX_CHUNK_CHARS = 12000
DEFAULT_WORKERS = 4
# A review request carries up to ~12k characters of code.
REVIEW_TIMEOUT_MS = 180000

MODEL_SYSTEM_PROMPT = (
    "You review added Python lines in Datrix, a multi-language code generator, against a fixed rule "
    "list. Lines starting with '+' were added by the change; lines starting with ' ' are context. "
    "Report only clear violations on '+' lines. For each: the line number, one rule id, 'quote' -- "
    "the offending code copied exactly from that line -- one short sentence of explanation, and your "
    "confidence. Do not reason in the output. Report nothing you are unsure of: an empty list is the "
    "normal answer, and a function that returns None or a default by documented design is not a "
    "violation. Rules:\n"
    + "\n".join(f"- {rule}: {text}" for rule, text in ADVISORY_RULES.items())
)

FINDINGS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "rule": {"type": "string", "enum": sorted(ADVISORY_RULES)},
                    "quote": {"type": "string", "maxLength": MAX_QUOTE_CHARS},
                    "explanation": {"type": "string", "maxLength": MAX_EXPLANATION_CHARS},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["line", "rule", "quote", "explanation", "confidence"],
            },
        }
    },
    "required": ["findings"],
}

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class PreReviewError(RuntimeError):
    """The review cannot run; the message says why and what to do."""


@dataclass(frozen=True)
class ChangedFile:
    repo: str
    path: str  # repository-relative, forward slashes
    abs_path: Path
    added: frozenset[int]

    @property
    def label(self) -> str:
        return f"{self.repo}/{self.path}"


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    explanation: str

    def render(self) -> str:
        return f"  {self.file}:{self.line} {self.rule}: {self.explanation}"


@dataclass
class ReviewResult:
    files: list[ChangedFile]
    definite: list[Finding] = field(default_factory=list)
    advisory: list[Finding] = field(default_factory=list)
    advisory_source: str = ""
    advisory_note: str = ""
    ungrounded: int = 0
    unreadable: int = 0

    def render(self) -> str:
        added = sum(len(f.added) for f in self.files)
        repos = len({f.repo for f in self.files})
        lines = [f"Pre-review of pending changes: {len(self.files)} Python files in {repos} repos "
                 f"({added} added lines)"]
        lines.append(f"DEFINITE ({len(self.definite)}):")
        lines.extend(finding.render() for finding in self.definite)
        if self.advisory_note:
            lines.append(f"ADVISORY: {self.advisory_note}")
        else:
            lines.append(f"ADVISORY ({len(self.advisory)}, from {self.advisory_source}; hypotheses -- "
                         f"verify each before acting):")
            lines.extend(finding.render() for finding in self.advisory)
            if self.ungrounded:
                lines.append(f"  ({self.ungrounded} model findings dropped: not high-confidence, not on an "
                             f"added line, or quoting code that line does not contain)")
            if self.unreadable:
                lines.append(f"  ({self.unreadable} model answers were not the requested JSON; those "
                             f"slices went unreviewed)")
        return "\n".join(lines)


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=GIT_TIMEOUT_SECONDS,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreReviewError(f"git {' '.join(args)} failed in {repo}: {exc}. Is git on PATH?") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PreReviewError(f"git {' '.join(args)} failed in {repo} (exit {result.returncode}): {detail}")
    return result.stdout.decode("utf-8", errors="replace")


def added_lines_by_path(diff: str) -> dict[str, set[int]]:
    """Map each new-side path in a ``--unified=0`` diff to the line numbers it adds."""
    added: dict[str, set[int]] = {}
    current: set[int] | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = None if target == "/dev/null" else added.setdefault(target.removeprefix("b/"), set())
            continue
        match = _HUNK_RE.match(line)
        if match and current is not None:
            start, count = int(match.group(1)), int(match.group(2) or "1")
            current.update(range(start, start + count))
    return added


def _has_head(repo: Path) -> bool:
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", "HEAD")
    except PreReviewError:
        return False
    return True


def changed_python_files(repo: Path) -> list[ChangedFile]:
    """The Python files with pending changes in ``repo`` and the lines each change adds."""
    added: dict[str, set[int]] = {}
    if _has_head(repo):
        diff = _git(repo, "diff", "HEAD", "--unified=0", "--no-color", "--no-ext-diff", "--", PYTHON_PATHSPEC)
        added.update(added_lines_by_path(diff))
        untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z", "--", PYTHON_PATHSPEC)
    else:
        untracked = _git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--",
                         PYTHON_PATHSPEC)
    for path in (p for p in untracked.split("\0") if p):
        abs_path = repo / path
        if abs_path.is_file():
            line_count = len(abs_path.read_text(encoding="utf-8", errors="replace").splitlines())
            added[path] = set(range(1, line_count + 1))
    return [
        ChangedFile(repo.name, path, repo / path, frozenset(lines))
        for path, lines in sorted(added.items())
        if lines and (repo / path).is_file()
    ]


def pending_python_changes(workspace: Path) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for repo in discover_repos(workspace):
        if _git(repo, "status", "--porcelain").strip():
            files.extend(changed_python_files(repo))
    return files


def _is_receiver(index: int, arg: ast.arg, in_class: bool) -> bool:
    return in_class and index == 0 and arg.arg in _RECEIVER_NAMES


def _untyped(node: ast.FunctionDef | ast.AsyncFunctionDef, in_class: bool) -> bool:
    positional = [*node.args.posonlyargs, *node.args.args]
    params = [a for i, a in enumerate(positional) if not _is_receiver(i, a, in_class)]
    params += [*node.args.kwonlyargs, *(a for a in (node.args.vararg, node.args.kwarg) if a is not None)]
    return node.returns is None or any(a.annotation is None for a in params)


def _name_of(node: ast.expr) -> str:
    """The trailing name of ``X``, ``mod.X``, ``X(...)`` or ``X[...]``."""
    if isinstance(node, (ast.Call, ast.Subscript)):
        return _name_of(node.func if isinstance(node, ast.Call) else node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ""


def _is_stub_statement(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
        return True
    return isinstance(stmt, ast.Raise) and stmt.exc is not None and _name_of(stmt.exc) == _NOT_IMPLEMENTED


def _is_placeholder(node: ast.FunctionDef | ast.AsyncFunctionDef, in_interface: bool) -> bool:
    if in_interface or any(_name_of(d) in _DECLARATION_DECORATORS for d in node.decorator_list):
        return False
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return all(_is_stub_statement(stmt) for stmt in body)


def _function_findings(tree: ast.Module) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []

    def visit(body: list[ast.stmt], in_class: bool, in_interface: bool) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _untyped(node, in_class):
                    hits.append((node.lineno, RULE_UNTYPED_DEF))
                if _is_placeholder(node, in_interface):
                    hits.append((node.lineno, RULE_PLACEHOLDER))
                visit(node.body, in_class=False, in_interface=False)
            elif isinstance(node, ast.ClassDef):
                interface = any(_name_of(base) in _INTERFACE_BASES for base in node.bases)
                visit(node.body, in_class=True, in_interface=interface)
            else:
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.stmt):
                        visit([child], in_class, in_interface)

    visit(tree.body, in_class=False, in_interface=False)
    return hits


def _is_get_none(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) == 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value is None
    )


def _swallows(handler: ast.ExceptHandler) -> bool:
    return all(
        isinstance(stmt, ast.Pass) or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                                       and stmt.value.value is Ellipsis)
        for stmt in handler.body
    )


def _expression_findings(tree: ast.Module) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if _is_get_none(node):
            hits.append((node.lineno, RULE_GET_NONE))
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                hits.append((node.lineno, RULE_BARE_EXCEPT))
            if _swallows(node):
                hits.append((node.lineno, RULE_EXCEPT_PASS))
    return hits


def _comment_findings(source: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and _TODO_RE.search(token.string):
                hits.append((token.start[0], RULE_TODO))
    except (tokenize.TokenError, SyntaxError):
        return hits
    return hits


def definite_findings(changed: ChangedFile, source: str) -> list[Finding]:
    """Deterministic findings on the added lines of one file."""
    try:
        tree = ast.parse(source, filename=changed.label)
    except SyntaxError as exc:
        return [Finding(changed.label, exc.lineno or 1, RULE_SYNTAX, f"{DEFINITE_EXPLANATIONS[RULE_SYNTAX]}: {exc.msg}")]
    hits = _function_findings(tree) + _expression_findings(tree) + _comment_findings(source)
    return [
        Finding(changed.label, line, rule, DEFINITE_EXPLANATIONS[rule])
        for line, rule in sorted(set(hits))
        if line in changed.added
    ]


def hunk_chunks(source_lines: list[str], added: frozenset[int], max_chars: int) -> list[str]:
    """The added lines with context, numbered and marked, split into chunks under ``max_chars``."""
    shown = sorted({n for line in added for n in range(line - CONTEXT_LINES, line + CONTEXT_LINES + 1)
                    if 1 <= n <= len(source_lines)})
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    previous = 0
    for number in shown:
        text = f"{'+' if number in added else ' '}{number:5d} {source_lines[number - 1]}"
        if previous and number != previous + 1:
            text = "  ...\n" + text
        if current and size + len(text) > max_chars:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(text)
        size += len(text) + 1
        previous = number
    if current:
        chunks.append("\n".join(current))
    return chunks


class UnreadableAnswer(ValueError):
    """A model answer that is not the findings JSON the schema asked for."""


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _grounded(item: dict[str, object], changed: ChangedFile, source_lines: list[str]) -> bool:
    """A finding stands only on an added line, at high confidence, quoting that line verbatim."""
    line, quote = item.get("line"), item.get("quote")
    if not isinstance(line, int) or line not in changed.added or not 1 <= line <= len(source_lines):
        return False
    if item.get("confidence") != KEPT_CONFIDENCE or not isinstance(quote, str) or not quote.strip():
        return False
    return _normalized(quote) in _normalized(source_lines[line - 1])


def parse_model_findings(text: str, changed: ChangedFile, source_lines: list[str]) -> tuple[list[Finding], int]:
    """Grounded findings from one model answer; returns (kept, dropped).

    Raises UnreadableAnswer when the answer is not the requested JSON object.
    """
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise UnreadableAnswer(f"not JSON: {exc}") from exc
    items = payload.get("findings") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise UnreadableAnswer("no 'findings' list")
    kept: list[Finding] = []
    dropped = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        rule, explanation = item.get("rule"), item.get("explanation")
        if rule not in ADVISORY_RULES or not isinstance(explanation, str) or not _grounded(item, changed,
                                                                                           source_lines):
            dropped += 1
            continue
        kept.append(Finding(changed.label, int(str(item["line"])), str(rule),
                            _normalized(explanation)[:MAX_EXPLANATION_CHARS]))
    return kept, dropped


@dataclass(frozen=True)
class _ChunkAnswer:
    kept: list[Finding]
    dropped: int
    unreadable: bool
    host: LocalHost


def _review_chunk(pool: LocalLlmPool, changed: ChangedFile, chunk: str, source_lines: list[str]) -> _ChunkAnswer:
    request = ChatRequest(
        system=MODEL_SYSTEM_PROMPT,
        user=f"File: {changed.label}\n\n{chunk}",
        temperature=MODEL_TEMPERATURE,
        max_tokens=MODEL_MAX_TOKENS,
        json_schema=FINDINGS_SCHEMA,
    )
    reply = pool.chat(request)
    try:
        kept, dropped = parse_model_findings(reply.text, changed, source_lines)
    except UnreadableAnswer:
        return _ChunkAnswer([], 0, True, reply.host)
    return _ChunkAnswer(kept, dropped, False, reply.host)


def advisory_review(result: ReviewResult, sources: dict[str, str], pool: LocalLlmPool, workers: int,
                    max_chars: int) -> None:
    lines_by_file = {changed.label: sources[changed.label].splitlines() for changed in result.files}
    # Test files get the definite checks only: measured, the model's findings there were
    # almost all noise, and the rules that matter most in tests are already hard bans.
    jobs = [
        (changed, chunk)
        for changed in result.files
        if not _TEST_PATH_RE.search(changed.path)
        for chunk in hunk_chunks(lines_by_file[changed.label], changed.added, max_chars)
    ]
    if not jobs:
        result.advisory_note = "nothing to review (only test files changed)"
        return
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            answers = list(executor.map(
                lambda job: _review_chunk(pool, job[0], job[1], lines_by_file[job[0].label]), jobs))
    except LocalLlmUnavailable as exc:
        result.advisory_note = f"skipped -- no local model server could answer. {exc}"
        return
    definite_keys = {(f.file, f.line) for f in result.definite}
    hosts: set[str] = set()
    for answer in answers:
        hosts.add(answer.host.label())
        result.ungrounded += answer.dropped
        result.unreadable += int(answer.unreadable)
        result.advisory.extend(f for f in answer.kept if (f.file, f.line) not in definite_keys)
    result.advisory.sort(key=lambda f: (f.file, f.line))
    result.advisory_source = ", ".join(sorted(hosts))


def review(workspace: Path, pool: LocalLlmPool | None, workers: int, max_chars: int) -> ReviewResult:
    files = pending_python_changes(workspace)
    result = ReviewResult(files)
    sources = {changed.label: changed.abs_path.read_text(encoding="utf-8", errors="replace") for changed in files}
    for changed in files:
        result.definite.extend(definite_findings(changed, sources[changed.label]))
    if pool is None:
        result.advisory_note = "not run (pass --model-review to ask a local model)"
    else:
        advisory_review(result, sources, pool, workers, max_chars)
    return result


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-review", action="store_true",
                        help="Also ask a local model for advisory findings (measured mostly false positives; "
                             "see the module docstring).")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel model requests.")
    parser.add_argument("--max-chunk-chars", type=int, default=DEFAULT_MAX_CHUNK_CHARS,
                        help="Largest slice of added code sent in one model request.")
    add_local_llm_arguments(parser, generate_timeout_ms=REVIEW_TIMEOUT_MS)
    args = parser.parse_args(argv)
    pool = LocalLlmPool(local_llm_settings(args)) if args.model_review else None
    try:
        result = review(get_datrix_root(), pool, args.workers, args.max_chunk_chars)
    except PreReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    if not result.files:
        print("No pending Python changes in any workspace repository.")
        return EXIT_CLEAN
    print(result.render())
    return EXIT_DEFINITE_FINDINGS if result.definite else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
