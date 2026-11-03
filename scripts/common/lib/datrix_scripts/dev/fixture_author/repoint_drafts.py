"""What repointing a test module sends a local model, and what it accepts back.

The model rewrites one test module at a time so that its tests read the shared fixture corpus: each test
whose input can be shared reads ``corpus_project("<entry>")`` (or ``corpus_project_copy`` when it writes
into the project) and names the service and block it reads; a test with a ``local`` reason keeps its input
in its package, marked with the first line ``// @local <reason>``. The answer is the whole new module and the
local fixture files it creates or replaces, all under the package's ``tests/fixtures/``.

Read before anything is written: the module parses; every file lies under the package's ``tests/fixtures/``,
is a fixture kind, and opens with ``// @local <reason>``; a string literal that looks like a raw secret and
the original did not hold refuses the module at once (it is queued, nothing written). Judged after it is
written: the module keeps every test it had, its assertion count (``assert`` statements plus
``pytest.raises`` blocks) has not fallen, it reads no input but a ``// @local`` one, and a module holding a
test with no local reason names a corpus accessor.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final

from datrix_testing.corpus import corpus_project, corpus_project_copy

from datrix_scripts.dev.fixture_author.drafting import secret_literal_lines
from datrix_scripts.dev.fixture_author.library_drafts import Rename
from datrix_scripts.dev.fixture_author.library_plan import InventoriedTest
from datrix_scripts.dev.fixture_author.needs import InputForm, ModuleInput, Unresolved
from datrix_scripts.dev.fixture_author.needs_reading import Declaration
from datrix_scripts.gates.ratchet.fixture_budget_gate import is_fixture
from datrix_scripts.skill.common import object_list

#: The first line of a fixture input that stays in its package, followed by why.
LOCAL_MARKER: Final = "// @local "
#: Where a package keeps its local fixture files, under the package directory.
FIXTURES_DIR: Final = PurePosixPath("tests", "fixtures")
#: The corpus accessors a repointed test reads its project through.
CORPUS_READERS: Final[frozenset[str]] = frozenset({corpus_project.__name__, corpus_project_copy.__name__})
#: The answer the model gives: the whole new module and the local fixture files it writes.
REPOINT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module": {"type": "string"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
                "required": ["path", "text"],
            },
        },
    },
    "required": ["module", "files"],
}

_TEST_PREFIX: Final = "test"
_CLASS_PREFIX: Final = "Test"
_RAISES: Final = "raises"
_PYTEST: Final = "pytest"
_PATH_BREAK: Final = re.compile(r"[./]")
_PLACEHOLDER: Final = "%("
_PARENT: Final = ".."


@dataclass(frozen=True)
class ModuleDraft:
    """A model's rewrite of one module: its whole text and the local fixture files (workspace-relative path,
    whole text) it creates or replaces."""

    module: str
    files: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class JobTest:
    """One test a module's rewrite serves: its label, the corpus entry it reads (``None`` when its input
    stays local), its needs with the renames applied, and why it stays local."""

    label: str
    entry: str | None
    needs: tuple[Declaration, ...]
    local: str | None


def local_reason(text: str) -> str | None:
    """Why the fixture *text* stays in its package: its first line ``// @local <reason>`` (leading blank lines
    and indentation of an inline literal ignored); ``None`` when it carries none."""
    first = text.lstrip("﻿").lstrip().partition("\n")[0].rstrip()
    if not first.startswith(LOCAL_MARKER):
        return None
    return first[len(LOCAL_MARKER):].strip() or None


def unshared_inputs(inputs: Iterable[ModuleInput]) -> list[str]:
    """Each input of *inputs* a repointed module may not read: one carrying no ``// @local`` first line, or a
    name that resolves to no one file for a reason other than naming no committed file."""
    found: list[str] = []
    for each in inputs:
        where = f"{each.form.value} {each.name!r} (module lines {list(each.lines)})"
        if each.form is not InputForm.INLINE and each.path is None:
            if each.unresolved is not Unresolved.NOT_FOUND:
                found.append(f"{where}: {each.unresolved}; read it from the corpus or a `// @local` file instead.")
            continue
        if local_reason(each.text) is None:
            found.append(f"{where} is read and its first line is not `{LOCAL_MARKER}<reason>`.")
    return found


def _is_raises(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    if isinstance(function, ast.Attribute):
        return function.attr == _RAISES and isinstance(function.value, ast.Name) and function.value.id == _PYTEST
    return isinstance(function, ast.Name) and function.id == _RAISES


def assertion_count(tree: ast.Module) -> int:
    """The assertions of *tree*: its ``assert`` statements plus its ``pytest.raises`` blocks."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.With | ast.AsyncWith):
            count += sum(1 for item in node.items if _is_raises(item.context_expr))
    return count


def defined_tests(tree: ast.Module) -> frozenset[str]:
    """The tests *tree* defines: each top-level ``test*`` function, and ``Class.test*`` of each ``Test*``
    class."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(_TEST_PREFIX):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith(_CLASS_PREFIX):
            names.update(
                f"{node.name}.{member.name}"
                for member in node.body
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef) and member.name.startswith(_TEST_PREFIX)
            )
    return frozenset(names)


def reads_corpus(tree: ast.Module) -> bool:
    """Whether *tree* names a corpus accessor (:data:`CORPUS_READERS`)."""
    return any(
        (isinstance(node, ast.Name) and node.id in CORPUS_READERS)
        or (isinstance(node, ast.Attribute) and node.attr in CORPUS_READERS)
        for node in ast.walk(tree)
    )


def unread_corpus(tests: Iterable[InventoriedTest], tree: ast.Module) -> list[str]:
    """Why *tree*, a module holding *tests*, is not repointed although it reads no input it may not: a test
    with no local reason reads a corpus entry, and the module names no corpus accessor. Building its own
    project (a name no committed file ends with) does not share it."""
    shared = sorted(test.name for test in tests if test.local is None)
    if not shared or reads_corpus(tree):
        return []
    return [f"the tests {shared} have no local reason, so each reads its corpus entry (corpus_project or "
            "corpus_project_copy); the module names neither."]


def parse_module_answer(answer: Mapping[str, object]) -> ModuleDraft | str:
    """The rewrite a model's JSON *answer* states, or why it states none."""
    module = answer.get("module")
    files = answer.get("files")
    if not isinstance(module, str) or not module.strip() or not isinstance(files, list):
        return 'the answer is not {"module": <the whole module text>, "files": [...]}.'
    pairs = [(item.get("path"), item.get("text")) for item in object_list(files)]
    if len(pairs) != len(files) or not all(isinstance(p, str) and isinstance(t, str) for p, t in pairs):
        return 'each entry of files is {"path": <workspace-relative path>, "text": <whole file text>}.'
    return ModuleDraft(module, tuple((str(path), str(text)) for path, text in pairs))


def draft_problems(package: str, draft: ModuleDraft) -> list[str]:
    """Why *draft* of a module of *package* cannot be written, read without writing anything."""
    problems: list[str] = []
    try:
        ast.parse(draft.module)
    except SyntaxError as error:
        problems.append(f"the module does not parse: {error.msg} at line {error.lineno}.")
    root = PurePosixPath(package) / FIXTURES_DIR
    paths = [path for path, _ in draft.files]
    for path, text in draft.files:
        pure = PurePosixPath(path)
        if pure.is_absolute() or _PARENT in pure.parts or not pure.is_relative_to(root):
            problems.append(f"file {path!r} is not under {root.as_posix()}/: a module writes only its package's "
                            "local fixtures.")
        elif not is_fixture(pure.name):
            problems.append(f"file {path!r} is not a fixture kind (.dtrx, .dtrx.false, .dcfg, .dseed).")
        if local_reason(text) is None:
            problems.append(f"file {path!r} does not open with `{LOCAL_MARKER}<reason>`.")
        if paths.count(path) > 1:
            problems.append(f"file {path!r} is listed more than once.")
    return list(dict.fromkeys(problems))


def _flagged_lines(text: str) -> set[str]:
    lines = text.splitlines()
    return {lines[number - 1].strip() for number in secret_literal_lines(text)}


def new_secret_sites(original: str, draft: ModuleDraft) -> list[str]:
    """Where *draft* holds a secret-looking literal (``<file>:<line>``) the *original* module did not hold;
    never the value."""
    held = _flagged_lines(original)
    lines = draft.module.splitlines()
    sites = [f"module:{number}" for number in secret_literal_lines(draft.module)
             if lines[number - 1].strip() not in held]
    sites.extend(f"{path}:{number}" for path, text in draft.files for number in secret_literal_lines(text))
    return sites


# --------------------------------------------------------------------------- prompts


REPOINT_RULES: Final = """You rewrite one Python test module of a Datrix package so that its tests read the shared fixture corpus instead of their own fixture files and inline .dtrx/.dcfg text.

Rules:
1. A test with an ENTRY reads the corpus: `from datrix_testing.corpus import corpus_project` and `corpus_project("<entry>")`, the entry .dtrx path, loaded the way the module loads a project now (for example through datrix_testing.project). The test names the service and the block it reads, by the names in its NEEDS; it never takes the first service and never counts across the whole system.
2. An absence assertion (the test proves a construct is missing) reads a service of the same entry that lacks the construct, by name.
3. A test that writes a project into tmp_path and changes it uses `from datrix_testing.corpus import corpus_project_copy` and `corpus_project_copy(tmp_path, "<entry>")`, which returns the copied entry; it never writes into the corpus.
4. A test with a LOCAL reason keeps its input in the package: an inline literal or a file under <package>/tests/fixtures/, whose first line is `// @local <reason>`. A parsed fragment whose text is the subject goes to <package>/tests/fixtures/parser/<construct>.dtrx (one file per construct family), or to <package>/tests/fixtures/parser/<syntax-error-kind>.dtrx.false; .dcfg text that config model tests load goes to <package>/tests/fixtures/config-kinds/<config kind>.dcfg.
5. After the rewrite the module reads no fixture file and no inline .dtrx/.dcfg text but those `// @local` inputs: each input under CURRENT INPUTS that is not local goes.
6. Keep every test function and every assertion: never remove or weaken an `assert` or a `pytest.raises` block. Keep the pytest markers (feature tags) and the imports the tests still use; drop the imports nothing uses.
7. Where RENAMES moves a need's path, read the new path.
8. Write no secret value; a credential appears by its handle only.

Answer with JSON: {"module": <the whole new module text>, "files": [{"path": <workspace-relative path under <package>/tests/fixtures/>, "text": <whole file text>}]}. List only the files you create or replace; a file another module reads is never replaced."""


def _need_line(need: Declaration) -> str:
    facts = f"; facts: {', '.join(need.facts)}" if need.facts else ""
    return f"    {need.kind} {need.path}{facts}"


def _test_lines(tests: Sequence[JobTest]) -> list[str]:
    lines: list[str] = []
    for test in tests:
        source = f"LOCAL {test.local}" if test.local is not None else f"ENTRY {test.entry}"
        lines.append(f"- {test.label}: {source}")
        lines.extend(_need_line(need) for need in test.needs)
    return lines or ["- (none)"]


def _input_line(each: ModuleInput) -> str:
    where = each.path.as_posix() if each.path is not None else str(each.unresolved or "inline text")
    return f"- {each.form.value} {each.name!r} (module lines {list(each.lines)}): {where}"


def need_names(needs: Iterable[Declaration]) -> frozenset[str]:
    """The declared names *needs* read: every segment of each path but the first (the system), placeholders
    dropped."""
    names: set[str] = set()
    for need in needs:
        segments = [segment for segment in _PATH_BREAK.split(need.path) if segment and _PLACEHOLDER not in segment]
        names.update(segments[1:] if len(segments) > 1 else segments)
    return frozenset(names)


@dataclass(frozen=True)
class ModulePrompt:
    """What one module's request carries besides the rules."""

    module: str
    text: str
    tests: tuple[JobTest, ...]
    run_files: tuple[str, ...]
    inputs: tuple[ModuleInput, ...]
    entry_files: Mapping[str, str]
    renames: tuple[Rename, ...]


def repoint_user_prompt(prompt: ModulePrompt, problems: Sequence[str], previous: ModuleDraft | None) -> str:
    """The request for *prompt*'s module, with the *problems* of its *previous* answer when there was one."""
    renames = json.dumps([rename.as_json() for rename in prompt.renames], indent=1) if prompt.renames else "(none)"
    sections = [
        f"MODULE: {prompt.module}",
        prompt.text,
        "TESTS (each with the corpus ENTRY it reads, or the LOCAL reason its input stays, and its NEEDS):",
        *_test_lines(prompt.tests),
        f"PROVEN BY: test.ps1 -Specific over {list(prompt.run_files)}",
        "CURRENT INPUTS:",
        *(_input_line(each) for each in prompt.inputs),
        "ENTRY FILES (each path relative to the corpus root; an entry is <entry>.dtrx):",
        *(f"=== {path} ===\n{text}" for path, text in prompt.entry_files.items()),
        f"RENAMES:\n{renames}",
    ]
    if problems:
        sections.append("PROBLEMS OF YOUR LAST ANSWER (it was not kept; the module is back to the text above):")
        sections.extend(f"- {problem}" for problem in problems)
    if previous is not None:
        sections.append(f"YOUR LAST MODULE:\n{previous.module}")
    return "\n\n".join(sections)


def module_queue_text(prompt: ModulePrompt, problems: Sequence[str], draft: ModuleDraft | None) -> str:
    """The queue file of a module a person finishes by hand: its tests, why the rewrite was not kept and the
    last draft."""
    lines = [
        f"# repoint {prompt.module}",
        "",
        "Finish by hand under the rules of `fixture-author.ps1 repoint`: the tests read the corpus entry named "
        "below by service and block name, local inputs open with `// @local <reason>`, every test and assertion "
        f"stays, and `test.ps1 -Specific` over {list(prompt.run_files)} passes. Then rerun "
        "`fixture-author.ps1 repoint -Package <package>`: a finished module leaves the queue.",
        "",
        "## Tests",
        *_test_lines(prompt.tests),
        "",
        "## Why it was not kept",
        *(f"- {problem}" for problem in problems or ["(no answer was kept)"]),
    ]
    if draft is not None:
        lines.extend(["", "## Last draft", "```python", draft.module, "```"])
        for path, text in draft.files:
            lines.extend(["", f"### {path}", "```", text, "```"])
    return "\n".join(lines) + "\n"


__all__ = [
    "CORPUS_READERS",
    "FIXTURES_DIR",
    "LOCAL_MARKER",
    "REPOINT_RULES",
    "REPOINT_SCHEMA",
    "JobTest",
    "ModuleDraft",
    "ModulePrompt",
    "assertion_count",
    "draft_problems",
    "local_reason",
    "module_queue_text",
    "need_names",
    "new_secret_sites",
    "parse_module_answer",
    "reads_corpus",
    "defined_tests",
    "repoint_user_prompt",
    "unread_corpus",
    "unshared_inputs",
]
