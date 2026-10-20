"""Coverage-driven unit test generation for Datrix projects using a local model.

Modes:
- report: list uncovered functions ranked by priority
- generate: generate test for top-ranked function (or --target-function)
- generate-all: attempt test generation for every ranked function

Every mode first runs the project's tests under coverage to find the uncovered functions.

Run by ``metrics/test-gen.ps1`` (POSIX twin ``test-gen.sh``): project names positionally or as
``--projects``, or ``--all``; ``--mode`` (or ``--generate`` / ``--generate-all``); ``--target-function``,
``--max-retries``, ``--min-uncovered-ratio``, ``--max-prompt-tokens``, ``--verbose-prompts``;
``--local-machines`` / ``--model`` (repeatable) / ``--llm-timeout`` seconds; ``--stop-on-error``;
``--verbose-output`` (numbered per-project lines); ``--self-test`` (no test is run, no model is asked).
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.llm_code_fix import parse_code_response
from datrix_scripts.local_llm import (
    ChatRequest,
    LocalLlmPool,
    LocalLlmUnavailable,
    add_wrapper_llm_arguments,
    wrapper_llm_settings,
)
from datrix_scripts.metrics.coverage import coverage_source
from datrix_scripts.metrics.projects import (
    EXIT_FAILED,
    EXIT_PASSED,
    SHOWCASE,
    STOP_MESSAGE,
    ProjectAnnouncer,
    ProjectSelectionError,
    SelectionWording,
    add_project_arguments,
    line_buffered_stdout,
    plant_workspace,
    print_stderr,
    print_summary,
    run_projects,
    select_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.metrics.test_gen"
WRAPPER: Final = "test-gen"
MODE_REPORT: Final = "report"
MODE_GENERATE: Final = "generate"
MODE_GENERATE_ALL: Final = "generate-all"
MODES: Final = (MODE_REPORT, MODE_GENERATE, MODE_GENERATE_ALL)
EXIT_NO_MODEL: Final = 2
# One generation request: a whole test module may come back, after reasoning.
DEFAULT_LLM_TIMEOUT_SECONDS: Final = 300
BOTH_GENERATE_SWITCHES: Final = "ERROR: Use only one of -Generate or -GenerateAll."
SUMMARY_TITLE: Final = "Test Generation Summary"
#: The summary joins a label and a project with one space (`` [PASS] <project>``).
_SUMMARY_SEPARATOR: Final = " "
WORDING: Final = SelectionWording(
    none_found="ERROR: No Datrix projects found in: {workspace}",
    none_valid=f"ERROR: No valid projects specified ({SHOWCASE} excluded).",
    none_given_heading=("ERROR: No projects specified.",),
    list_available=False,
)
USAGE_LINES: Final = ("Usage: .\\test-gen.ps1 <project-name> [-Mode report|generate|generate-all]",)
GENERATE_MAX_TOKENS = 32768
GENERATE_TEMPERATURE = 0.3

DEFAULT_UNCOVERED_RATIO = 0.5
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_PROMPT_TOKENS = 6000
PROMPT_WARNING_TOKENS = 4000
MAX_RELEVANT_IMPORTS = 20
MAX_RELATED_TEST_FILES = 3
MAX_TEST_NAMES_PER_FILE = 8
MAX_RELEVANT_CLASS_METHODS = 5
MANIFEST_VERSION = 1

SYSTEM_PROMPT = """Generate a complete pytest file for the target Datrix function.

Mandatory:
- pytest only; no unittest.mock, MagicMock, patch, or SimpleNamespace.
- Use real objects/factories when available.
- Import the target from the exact module path provided.
- Add @pytest.mark.unit to each test.
- Return only ASCII Python inside one ```python code fence.
- Use unique test_<function>_<scenario> names.
- Respect type hints; do not pass None for non-Optional parameters.
- Prefer tiny local real helper classes for simple attribute-only inputs.
- Do not instantiate imported domain classes unless their constructor is shown.
- Do not import or instantiate annotation-only types from signatures.
- Test doubles must implement every attribute/method the target calls.
- For acc.add(category, name, default), the env var name is the second argument.
- Do not invent category names; use category constants/literals from the target.
- For imported-helper exceptions, assert type only unless exact text is in the target body.
- Do not invent package import paths.
- Cover useful happy/error paths without duplicating listed existing tests.
"""


@dataclass(frozen=True)
class FunctionCandidate:
    """Function-level coverage gap candidate."""

    file_path: Path
    module_path: str
    function_name: str
    class_name: str | None
    start_line: int
    end_line: int
    total_lines: int
    uncovered_lines: int
    uncovered_ratio: float
    complexity: int
    has_type_hints: bool
    has_docstring: bool
    score: int

    @property
    def id(self) -> str:
        class_prefix = f"{self.class_name}." if self.class_name else ""
        return (
            f"{self.file_path}:{self.start_line}:{class_prefix}{self.function_name}"
        )


@dataclass(frozen=True)
class GenerationResult:
    """Result for one generation attempt."""

    candidate: FunctionCandidate
    generated_file: Path | None
    success: bool
    detail: str


@dataclass(frozen=True)
class AddedTest:
    """Generated test file kept after validation."""

    path: Path
    candidate: FunctionCandidate


def _run_coverage_json(project_root: Path, report_path: Path) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        f"--cov={coverage_source(project_root)}",
        f"--cov-report=json:{report_path}",
        "--override-ini=addopts=",
        "-q",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        return False, f"pytest not found: {exc}"

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr if stderr else stdout
        return False, f"pytest coverage run failed: {detail}"
    return True, ""


def _resolve_coverage_file_path(project_root: Path, file_str: str) -> Path:
    file_path = Path(file_str)
    if not file_path.is_absolute():
        file_path = project_root / file_path
    return file_path.resolve()


def _load_coverage_missing_lines(
    report_path: Path,
    project_root: Path,
) -> dict[Path, set[int]]:
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    files_obj = raw.get("files")
    if not isinstance(files_obj, dict):
        return {}

    out: dict[Path, set[int]] = {}
    for file_str, file_data in files_obj.items():
        if not isinstance(file_data, dict):
            continue
        missing = file_data.get("missing_lines")
        if not isinstance(missing, list):
            continue
        out[_resolve_coverage_file_path(project_root, file_str)] = {
            int(line) for line in missing
        }
    return out


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _enclosing_class_name(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> str | None:
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, ast.ClassDef):
            return current.name
    return None


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _contains_validator_or_transformer(text: str) -> bool:
    lower = text.lower()
    keys = ("validate", "validator", "transform", "parser", "parse")
    return any(k in lower for k in keys)


def _is_config_or_utility(path: Path) -> bool:
    lower = str(path).replace("\\", "/").lower()
    return any(part in lower for part in ("/config/", "/util", "/helper"))


def _has_type_hints(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if node.returns is not None:
        return True
    for arg in (
        list(node.args.args)
        + list(node.args.kwonlyargs)
        + list(node.args.posonlyargs)
    ):
        if arg.annotation is not None:
            return True
    return node.args.vararg is not None and node.args.vararg.annotation is not None


def _estimate_complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    complexity = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.Try,
                ast.IfExp,
                ast.With,
                ast.AsyncWith,
                ast.Match,
                ast.comprehension,
            ),
        ):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(1, len(child.values) - 1)
    return complexity


def _score_candidate(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    function_name: str,
    file_path: Path,
    complexity: int,
    has_type_hints: bool,
    has_docstring: bool,
) -> int:
    score = 0
    if _is_public(function_name):
        score += 3
    if _contains_validator_or_transformer(function_name) or _contains_validator_or_transformer(
        str(file_path)
    ):
        score += 2
    if complexity > 5:
        score += 2
    if has_type_hints:
        score += 1
    if has_docstring:
        score += 1
    if _is_config_or_utility(file_path):
        score += 1
    # Make sorting deterministic for ties by preferring smaller functions.
    score += max(0, 3 - min(3, (node.end_lineno or node.lineno) - node.lineno))
    return score


def _to_module_path(project_root: Path, file_path: Path) -> str:
    rel = file_path.relative_to((project_root / "src").resolve())
    without_suffix = rel.with_suffix("")
    return ".".join(without_suffix.parts)


def _candidate_manifest_key(project_root: Path, candidate: FunctionCandidate) -> str:
    try:
        rel_file = candidate.file_path.relative_to(project_root.resolve())
    except ValueError:
        rel_file = candidate.file_path
    class_prefix = f"{candidate.class_name}." if candidate.class_name else ""
    return f"{rel_file.as_posix()}:{candidate.start_line}:{class_prefix}{candidate.function_name}"


def _output_dir(project_root: Path) -> Path:
    """Workspace-level output folder holding this project's test-gen state.

    Never inside the package repo. Every datrix-* package is its own git
    repository, so a manifest or report written into one is committed and pushed
    unless a human notices; the repo-level ignored-source gate fails on any such
    stray output. Losing this folder is only a slowdown -- an already-generated
    test is also skipped because its output file exists.
    """
    return WORKSPACE_DIR / ".test-output" / "test-gen" / project_root.name


def _manifest_path(project_root: Path) -> Path:
    return _output_dir(project_root) / "test-gen-manifest.json"


def _load_manifest(project_root: Path) -> dict[str, object]:
    path = _manifest_path(project_root)
    if not path.exists():
        return {"version": MANIFEST_VERSION, "generated": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": MANIFEST_VERSION, "generated": {}}
    if not isinstance(raw, dict):
        return {"version": MANIFEST_VERSION, "generated": {}}
    generated = raw.get("generated")
    if not isinstance(generated, dict):
        raw["generated"] = {}
    raw["version"] = MANIFEST_VERSION
    return raw


def _save_manifest(project_root: Path, manifest: dict[str, object]) -> None:
    path = _manifest_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _manifest_generated(manifest: dict[str, object]) -> dict[str, object]:
    generated = manifest.get("generated")
    if isinstance(generated, dict):
        return generated
    generated = {}
    manifest["generated"] = generated
    return generated


def _is_candidate_already_generated(
    project_root: Path,
    manifest: dict[str, object],
    candidate: FunctionCandidate,
) -> bool:
    entry = _manifest_generated(manifest).get(
        _candidate_manifest_key(project_root, candidate)
    )
    if not isinstance(entry, dict):
        return False
    if entry.get("status") != "success":
        return False
    path_value = entry.get("path")
    return isinstance(path_value, str) and (project_root / path_value).exists()


def _record_generated_test(
    project_root: Path,
    manifest: dict[str, object],
    candidate: FunctionCandidate,
    generated_file: Path,
    model: str,
) -> None:
    try:
        rel_path = generated_file.relative_to(project_root).as_posix()
    except ValueError:
        rel_path = generated_file.as_posix()
    _manifest_generated(manifest)[_candidate_manifest_key(project_root, candidate)] = {
        "candidate_id": candidate.id,
        "model": model,
        "path": rel_path,
        "status": "success",
    }
    _save_manifest(project_root, manifest)


def _collect_candidates(
    project_root: Path,
    missing_by_file: dict[Path, set[int]],
    min_uncovered_ratio: float,
) -> list[FunctionCandidate]:
    candidates: list[FunctionCandidate] = []

    for file_path, missing_lines in sorted(missing_by_file.items()):
        src_root = (project_root / "src").resolve()
        if not str(file_path).startswith(str(src_root)):
            continue
        if not file_path.is_file() or file_path.suffix != ".py":
            continue

        source = file_path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        parents = _build_parent_map(tree)
        module_path = _to_module_path(project_root, file_path)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.end_lineno is None:
                continue

            start = node.lineno
            end = node.end_lineno
            total = max(1, end - start + 1)
            uncovered = sum(1 for line in missing_lines if start <= line <= end)
            ratio = uncovered / total
            if ratio <= min_uncovered_ratio:
                continue

            func_name = node.name
            class_name = _enclosing_class_name(node, parents)
            complexity = _estimate_complexity(node)
            has_hints = _has_type_hints(node)
            has_doc = ast.get_docstring(node) is not None
            score = _score_candidate(
                node,
                func_name,
                file_path,
                complexity,
                has_hints,
                has_doc,
            )
            candidates.append(
                FunctionCandidate(
                    file_path=file_path,
                    module_path=module_path,
                    function_name=func_name,
                    class_name=class_name,
                    start_line=start,
                    end_line=end,
                    total_lines=total,
                    uncovered_lines=uncovered,
                    uncovered_ratio=ratio,
                    complexity=complexity,
                    has_type_hints=has_hints,
                    has_docstring=has_doc,
                    score=score,
                )
            )

    candidates.sort(
        key=lambda c: (
            -c.score,
            -c.uncovered_ratio,
            -c.complexity,
            str(c.file_path),
            c.start_line,
        )
    )
    return candidates


def _extract_source_segment(
    source_lines: list[str],
    start: int,
    end: int,
) -> str:
    return "\n".join(source_lines[start - 1 : end])


def _dedent_block(text: str) -> str:
    lines = text.splitlines()
    indents = [
        len(line) - len(line.lstrip())
        for line in lines
        if line.strip()
    ]
    if not indents:
        return text
    indent = min(indents)
    return "\n".join(line[indent:] if len(line) >= indent else line for line in lines)


def _find_function_node(
    tree: ast.Module,
    candidate: FunctionCandidate,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != candidate.function_name or node.lineno != candidate.start_line:
            continue
        return node
    return None


def _referenced_names(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            names.add(child.id)
        elif isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
            names.add(child.value.id)
    return names


def _import_alias_matches(alias: ast.alias, referenced: set[str]) -> bool:
    alias_name = alias.asname or alias.name.split(".", 1)[0]
    return alias_name in referenced or alias.name in referenced


def _extract_node_source(source_lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start) or start
    return _dedent_block("\n".join(source_lines[start - 1 : end]))


def _extract_import_lines(
    tree: ast.Module,
    source_lines: list[str],
    function_node: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> str:
    referenced = _referenced_names(function_node)
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            if any(_import_alias_matches(alias, referenced) for alias in node.names):
                imports.append(_extract_node_source(source_lines, node))
        elif isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" or _import_alias_matches(alias, referenced) for alias in node.names):
                imports.append(_extract_node_source(source_lines, node))
        if len(imports) >= MAX_RELEVANT_IMPORTS:
            break
    return "\n".join(imports[:MAX_RELEVANT_IMPORTS])


def _extract_local_context(
    tree: ast.Module,
    source_lines: list[str],
    function_node: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> str:
    referenced = _referenced_names(function_node)
    snippets: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = _assignment_target_names(node)
            if targets & referenced:
                snippets.append(_extract_node_source(source_lines, node))
        elif isinstance(node, ast.ClassDef) and node.name in referenced:
            snippets.append(_summarize_class_for_prompt(node, source_lines))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in referenced:
            snippets.append(_extract_signature_from_node(node, source_lines))
        if len(snippets) >= 8:
            break
    return "\n\n".join(snippets)


def _extract_string_literals(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    values: list[str] = []
    seen: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Constant) or not isinstance(child.value, str):
            continue
        value = child.value
        if value == "":
            continue
        if value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values[:30]


def _format_string_literals(values: list[str]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {value}" for value in values)


def _extract_attribute_accesses(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    values: list[str] = []
    seen: set[str] = set()
    for child in ast.walk(node):
        name: str | None = None
        if isinstance(child, ast.Attribute):
            name = _attribute_chain(child)
        elif isinstance(child, ast.Call):
            name = _getattr_access(child) or _helper_required_attribute(child)
        if name is None or name in seen:
            continue
        seen.add(name)
        values.append(name)
    return values[:30]


def _attribute_chain(node: ast.Attribute) -> str | None:
    parts = [node.attr]
    current = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _getattr_access(node: ast.Call) -> str | None:
    if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
        return None
    if len(node.args) < 2:
        return None
    target, attr = node.args[0], node.args[1]
    if not isinstance(target, ast.Name):
        return None
    if not isinstance(attr, ast.Constant) or not isinstance(attr.value, str):
        return None
    return f"{target.id}.{attr.value}"


def _helper_required_attribute(node: ast.Call) -> str | None:
    if not isinstance(node.func, ast.Name) or not node.args:
        return None
    first_arg = node.args[0]
    if not isinstance(first_arg, ast.Name):
        return None
    if node.func.id == "engine_str":
        return f"{first_arg.id}.engine"
    return None


def _format_attribute_accesses(values: list[str]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {value}" for value in values)


def _assignment_target_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets: list[ast.expr]
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    else:
        targets = [node.target]
    names: set[str] = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
    return names


def _summarize_class_for_prompt(node: ast.ClassDef, source_lines: list[str]) -> str:
    header = source_lines[node.lineno - 1].strip()
    methods = [
        _indent_block(_extract_node_source(source_lines, child), "    ")
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ][:MAX_RELEVANT_CLASS_METHODS]
    if not methods:
        return header
    return header + "\n" + "\n".join(methods)


def _indent_block(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else line for line in text.splitlines())


def _extract_signature_from_node(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: list[str],
) -> str:
    signature_lines: list[str] = []
    paren_balance = 0
    end = node.end_lineno or node.lineno
    for line in source_lines[node.lineno - 1 : end]:
        signature_lines.append(line.strip())
        paren_balance += line.count("(") - line.count(")")
        if line.strip().endswith(":") and paren_balance <= 0:
            break
    return "\n".join(signature_lines)


def _extract_class_context(
    tree: ast.Module,
    source_lines: list[str],
    class_name: str | None,
    target_name: str,
) -> str:
    if class_name is None:
        return ""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name and node.end_lineno:
            header = source_lines[node.lineno - 1]
            method_names = [
                n.name
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            relevant = _select_relevant_method_names(method_names, target_name)
            return (
                f"{header}\n"
                f"Method count: {len(method_names)}\n"
                f"Relevant methods: {', '.join(relevant) if relevant else 'none'}"
            )
    return ""


def _select_relevant_method_names(
    method_names: list[str],
    target_name: str,
) -> list[str]:
    target_parts = {part for part in target_name.lower().split("_") if part}

    def score(name: str) -> tuple[int, str]:
        parts = {part for part in name.lower().split("_") if part}
        overlap = len(parts & target_parts)
        init_bonus = 1 if name == "__init__" else 0
        target_bonus = 2 if name == target_name else 0
        return (target_bonus + init_bonus + overlap, name)

    ranked = sorted(method_names, key=score, reverse=True)
    return ranked[:MAX_RELEVANT_CLASS_METHODS]


def _iter_test_files(project_root: Path) -> list[Path]:
    tests_dir = project_root / "tests"
    if not tests_dir.is_dir():
        return []
    return sorted(
        path
        for path in tests_dir.rglob("*.py")
        if path.is_file() and path.name != "__init__.py"
    )


def _find_related_test_files(
    project_root: Path,
    candidate: FunctionCandidate,
) -> list[Path]:
    module_stem = candidate.file_path.stem
    search_terms = {
        module_stem,
        candidate.module_path,
        candidate.function_name,
    }
    if candidate.class_name is not None:
        search_terms.add(candidate.class_name)

    related: list[tuple[int, Path]] = []
    direct = project_root / "tests" / "unit" / f"test_{module_stem}.py"
    if direct.exists():
        related.append((100, direct))

    for test_file in _iter_test_files(project_root):
        if any(path == test_file for _, path in related):
            continue
        score = 0
        if module_stem in test_file.stem:
            score += 30
        text = test_file.read_text(encoding="utf-8", errors="replace")
        for term in search_terms:
            if term in text:
                score += 10
        if candidate.function_name in text:
            score += 30
        if score > 0:
            related.append((score, test_file))
    return [
        path
        for _, path in sorted(related, key=lambda item: (-item[0], str(item[1])))
    ][:MAX_RELATED_TEST_FILES]


def _build_existing_test_context(
    project_root: Path,
    candidate: FunctionCandidate,
) -> str:
    chunks: list[str] = []
    for test_file in _find_related_test_files(project_root, candidate):
        try:
            rel_path = test_file.relative_to(project_root)
        except ValueError:
            rel_path = test_file
        try:
            tree = ast.parse(test_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            test_names: list[str] = []
        else:
            test_names = sorted(_collect_test_function_names_from_tree(tree))
        if test_names:
            shown = test_names[:MAX_TEST_NAMES_PER_FILE]
            names = "\n".join(f"- {name}" for name in shown)
            if len(test_names) > len(shown):
                names += f"\n- ... {len(test_names) - len(shown)} more"
        else:
            names = "- no parseable test functions"
        chunks.append(f"{rel_path.as_posix()}\n{names}")
    return "\n\n".join(chunks)


def _collect_test_function_names_from_tree(tree: ast.AST) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _collect_existing_test_function_names(project_root: Path) -> set[str]:
    names: set[str] = set()
    for test_file in _iter_test_files(project_root):
        try:
            tree = ast.parse(test_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        names.update(_collect_test_function_names_from_tree(tree))
    return names


def _build_generated_test_path(project_root: Path, candidate: FunctionCandidate) -> Path:
    tests_unit = project_root / "tests" / "unit"
    module_stem = candidate.file_path.stem
    fn_stem = candidate.function_name.lower()
    class_stem = (
        f"_{candidate.class_name.lower()}" if candidate.class_name is not None else ""
    )
    name = f"test_{module_stem}{class_stem}_{fn_stem}_generated.py"
    return tests_unit / name


def _build_target_import_line(candidate: FunctionCandidate) -> str:
    if candidate.class_name is None:
        return f"from {candidate.module_path} import {candidate.function_name}"
    return f"from {candidate.module_path} import {candidate.class_name}"


def _estimate_prompt_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _maybe_report_prompt(
    prompt: str,
    *,
    label: str,
    max_prompt_tokens: int,
    verbose_prompts: bool,
) -> None:
    token_estimate = _estimate_prompt_tokens(prompt)
    if token_estimate > PROMPT_WARNING_TOKENS:
        print(
            f"Warning: {label} prompt is about {token_estimate} tokens "
            f"(budget={max_prompt_tokens}).",
            file=sys.stderr,
        )
    if token_estimate > max_prompt_tokens:
        print(
            f"Warning: {label} prompt exceeds --max-prompt-tokens.",
            file=sys.stderr,
        )
    if verbose_prompts:
        print(f"\n--- {label} prompt ({token_estimate} tokens est.) ---")
        print(prompt)
        print(f"--- end {label} prompt ---\n")


def _build_user_prompt(project_root: Path, candidate: FunctionCandidate) -> str:
    source_text = candidate.file_path.read_text(encoding="utf-8", errors="replace")
    source_lines = source_text.splitlines()
    tree = ast.parse(source_text)
    function_node = _find_function_node(tree, candidate)

    # Use the AST function span instead of coverage line spans; coverage can
    # stop on the final executable line and omit closing syntax.
    function_source = (
        _extract_node_source(source_lines, function_node)
        if function_node is not None
        else _extract_source_segment(source_lines, candidate.start_line, candidate.end_line)
    )
    # Keep only imports referenced by the target body. This is the largest prompt
    # reduction for modules with broad import blocks.
    imports_text = _extract_import_lines(tree, source_lines, function_node)
    class_context = _extract_class_context(
        tree,
        source_lines,
        candidate.class_name,
        candidate.function_name,
    )
    local_context = _extract_local_context(tree, source_lines, function_node)
    string_literals = _format_string_literals(_extract_string_literals(function_node))
    attribute_accesses = _format_attribute_accesses(
        _extract_attribute_accesses(function_node)
    )
    existing_test_context = _build_existing_test_context(project_root, candidate)
    import_line = _build_target_import_line(candidate)

    return (
        f"Target function: {candidate.id}\n\n"
        f"Module import path:\n{import_line}\n\n"
        "Function source:\n"
        f"```python\n{function_source}\n```\n\n"
        "Class context (if method):\n"
        f"```python\n{class_context or '# none'}\n```\n\n"
        "File imports:\n"
        f"```python\n{imports_text}\n```\n\n"
        "Referenced local definitions/constants:\n"
        f"```python\n{local_context or '# none'}\n```\n\n"
        "String literals in target body (prefer these exact expected values):\n"
        f"{string_literals}\n\n"
        "Attributes/methods the target reads or calls (test doubles must provide these):\n"
        f"{attribute_accesses}\n\n"
        "Existing related test summary (do not duplicate these scenarios):\n"
        f"{existing_test_context or '- none'}\n"
    )


def _build_retry_prompt(
    candidate: FunctionCandidate,
    retry_feedback: str,
) -> str:
    signature = _extract_function_signature(candidate)
    imports_text = _extract_relevant_imports_for_candidate(candidate)
    function_node = _function_node_for_candidate(candidate)
    string_literals = _format_string_literals(_extract_string_literals(function_node))
    attribute_accesses = _format_attribute_accesses(
        _extract_attribute_accesses(function_node)
    )
    local_context = _extract_local_context_for_candidate(candidate)
    return (
        "Previous generated test failed validation. Return a corrected complete "
        "pytest file.\n\n"
        f"Target function: {candidate.id}\n"
        f"Required import: {_build_target_import_line(candidate)}\n"
        f"Exact signature:\n```python\n{signature}\n```\n"
        f"Relevant imports from source file:\n```python\n{imports_text}\n```\n"
        f"Referenced local definitions/constants:\n```python\n{local_context or '# none'}\n```\n"
        "String literals in target body (prefer these exact expected values):\n"
        f"{string_literals}\n"
        "Attributes/methods the target reads or calls:\n"
        f"{attribute_accesses}\n"
        f"Validation error:\n{retry_feedback}\n"
    )


def _function_node_for_candidate(
    candidate: FunctionCandidate,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    source_text = candidate.file_path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source_text)
    return _find_function_node(tree, candidate)


def _extract_relevant_imports_for_candidate(candidate: FunctionCandidate) -> str:
    source_text = candidate.file_path.read_text(encoding="utf-8", errors="replace")
    source_lines = source_text.splitlines()
    tree = ast.parse(source_text)
    function_node = _find_function_node(tree, candidate)
    return _extract_import_lines(tree, source_lines, function_node)


def _extract_local_context_for_candidate(candidate: FunctionCandidate) -> str:
    source_text = candidate.file_path.read_text(encoding="utf-8", errors="replace")
    source_lines = source_text.splitlines()
    tree = ast.parse(source_text)
    function_node = _find_function_node(tree, candidate)
    return _extract_local_context(tree, source_lines, function_node)


def _extract_function_signature(candidate: FunctionCandidate) -> str:
    source_lines = candidate.file_path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()
    signature_lines: list[str] = []
    paren_balance = 0
    for line in source_lines[candidate.start_line - 1 : candidate.end_line]:
        signature_lines.append(line)
        paren_balance += line.count("(") - line.count(")")
        stripped = line.strip()
        if stripped.endswith(":") and paren_balance <= 0:
            break
    return "\n".join(signature_lines)


def _validate_generated_test(
    test_file_path: Path,
    generated_content: str,
    project_root: Path,
    candidate: FunctionCandidate,
) -> tuple[bool, str]:
    try:
        generated_tree = ast.parse(generated_content)
    except SyntaxError as exc:
        return False, f"ast.parse failed: {exc}"

    generated_names = _collect_test_function_names_from_tree(generated_tree)
    if not generated_names:
        return False, "generated file contains no test_* functions"
    if candidate.function_name not in generated_content:
        return False, (
            "generated file does not reference target function "
            f"{candidate.function_name}"
        )
    if candidate.module_path not in generated_content:
        return False, (
            "generated file does not import or reference target module "
            f"{candidate.module_path}"
        )
    existing_names = _collect_existing_test_function_names(project_root)
    duplicate_names = sorted(generated_names & existing_names)
    if duplicate_names:
        return False, "duplicate existing test function names: " + ", ".join(
            duplicate_names
        )

    test_file_path.parent.mkdir(parents=True, exist_ok=True)
    test_file_path.write_text(generated_content, encoding="utf-8", newline="\n")

    ruff_fix_cmd = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--fix",
        str(test_file_path),
    ]
    try:
        subprocess.run(
            ruff_fix_cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        test_file_path.unlink(missing_ok=True)
        return False, "ruff fix failed: ruff not found in environment"

    ruff_cmd = [sys.executable, "-m", "ruff", "check", str(test_file_path)]
    try:
        ruff_result = subprocess.run(
            ruff_cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        test_file_path.unlink(missing_ok=True)
        return False, "ruff check failed: ruff not found in environment"
    if ruff_result.returncode != 0:
        detail = ruff_result.stdout.strip() or ruff_result.stderr.strip()
        test_file_path.unlink(missing_ok=True)
        return False, f"ruff check failed: {detail}"

    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file_path),
        "-x",
        "-q",
        "--tb=short",
        "--no-cov",
        "--override-ini=addopts=",
    ]
    pytest_result = subprocess.run(
        pytest_cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if pytest_result.returncode != 0:
        detail = pytest_result.stdout.strip() or pytest_result.stderr.strip()
        test_file_path.unlink(missing_ok=True)
        return False, f"pytest failed: {detail}"

    project_pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-x",
        "-q",
        "--tb=short",
        "--no-cov",
        "--override-ini=addopts=",
    ]
    project_pytest_result = subprocess.run(
        project_pytest_cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if project_pytest_result.returncode != 0:
        detail = (
            project_pytest_result.stdout.strip()
            or project_pytest_result.stderr.strip()
        )
        test_file_path.unlink(missing_ok=True)
        return False, f"project pytest failed; generated test deleted: {detail}"

    return True, "ok"


def _try_generate_for_candidate(
    project_root: Path,
    candidate: FunctionCandidate,
    manifest: dict[str, object],
    max_retries: int,
    max_prompt_tokens: int,
    verbose_prompts: bool,
    pool: LocalLlmPool,
) -> GenerationResult:
    if _is_candidate_already_generated(project_root, manifest, candidate):
        return GenerationResult(
            candidate=candidate,
            generated_file=None,
            success=False,
            detail="skip: candidate already recorded in test-gen manifest",
        )

    output_path = _build_generated_test_path(project_root, candidate)
    if output_path.exists():
        return GenerationResult(
            candidate=candidate,
            generated_file=None,
            success=False,
            detail=f"skip: generated test already exists ({output_path})",
        )

    prompt_base = _build_user_prompt(project_root, candidate)
    _maybe_report_prompt(
        prompt_base,
        label="initial",
        max_prompt_tokens=max_prompt_tokens,
        verbose_prompts=verbose_prompts,
    )
    retry_feedback = ""

    for attempt in range(1, max_retries + 1):
        # Retries are intentionally small: local models were failing when the
        # full context was resent with growing feedback appended.
        if retry_feedback:
            prompt = _build_retry_prompt(candidate, retry_feedback)
            _maybe_report_prompt(
                prompt,
                label=f"retry-{attempt}",
                max_prompt_tokens=max_prompt_tokens,
                verbose_prompts=verbose_prompts,
            )
        else:
            prompt = prompt_base

        reply = pool.chat(ChatRequest(
            system=SYSTEM_PROMPT,
            user=prompt,
            temperature=GENERATE_TEMPERATURE,
            max_tokens=GENERATE_MAX_TOKENS,
        ))
        parsed = parse_code_response(reply.text)
        if parsed is None:
            retry_feedback = "Could not parse Python code fence from the model response."
            continue

        ok, detail = _validate_generated_test(
            output_path,
            parsed,
            project_root,
            candidate,
        )
        if ok:
            _record_generated_test(
                project_root,
                manifest,
                candidate,
                output_path,
                reply.host.model,
            )
            return GenerationResult(
                candidate=candidate,
                generated_file=output_path,
                success=True,
                detail="generated and validated with project tests",
            )

        retry_feedback = detail

    if output_path.exists():
        output_path.unlink(missing_ok=True)
    return GenerationResult(
        candidate=candidate,
        generated_file=None,
        success=False,
        detail=f"failed after {max_retries} retries: {retry_feedback}",
    )


def _print_report(candidates: list[FunctionCandidate]) -> None:
    if not candidates:
        print("No uncovered functions matched the filter.")
        return
    print("Ranked uncovered functions:")
    for idx, c in enumerate(candidates, start=1):
        cls = f"{c.class_name}." if c.class_name else ""
        print(
            f"{idx:03d}. score={c.score:02d} ratio={c.uncovered_ratio:.2f} "
            f"complexity={c.complexity:02d} "
            f"{c.file_path}:{c.start_line} {cls}{c.function_name}"
        )


def _select_target(
    candidates: list[FunctionCandidate],
    target_function: str | None,
) -> list[FunctionCandidate]:
    if target_function is None:
        return candidates

    target = target_function.strip()
    filtered = [
        c
        for c in candidates
        if target in _candidate_target_keys(c) or c.id.endswith(f":{target}")
    ]
    return filtered


def _candidate_target_keys(candidate: FunctionCandidate) -> set[str]:
    keys = {
        candidate.function_name,
        f"{candidate.module_path}.{candidate.function_name}",
        candidate.id,
    }
    if candidate.class_name is not None:
        keys.add(f"{candidate.class_name}.{candidate.function_name}")
        keys.add(
            f"{candidate.module_path}.{candidate.class_name}.{candidate.function_name}"
        )
    return keys


def _format_candidate_ref(candidate: FunctionCandidate) -> str:
    cls = f"{candidate.class_name}." if candidate.class_name else ""
    return f"{candidate.module_path}.{cls}{candidate.function_name} ({candidate.id})"


def _is_skipped_result(result: GenerationResult) -> bool:
    return result.detail.startswith("skip:")


def _print_added_tests(added_tests: list[AddedTest]) -> None:
    if not added_tests:
        print("Added tests: none")
        return
    print("Added tests:")
    for added in added_tests:
        print(f" - {added.path} for {added.candidate.id}")


def run_project(args: argparse.Namespace, project_root: Path) -> int:
    """One project's run in ``args.mode``: its tests under coverage, then the ranked uncovered functions
    reported or tests generated for them. 1 when the project, its src/ or its tests/ is missing or the
    coverage run fails; 2 when no local model server can answer."""
    project_root = project_root.resolve()
    if not project_root.is_dir():
        print_stderr(f"Error: project root is not a directory: {project_root}")
        return EXIT_FAILED
    if not all((project_root / marker.value).is_dir() for marker in (PackageMarker.SRC, PackageMarker.TESTS)):
        print_stderr("Error: project root must contain src/ and tests/ directories.")
        return EXIT_FAILED

    report_path = _output_dir(project_root) / "coverage.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    ok, err = _run_coverage_json(project_root, report_path)
    if not ok:
        print_stderr(err)
        return EXIT_FAILED
    if not report_path.exists():
        print_stderr("Coverage JSON report was not produced by pytest-cov.")
        return EXIT_FAILED

    missing_by_file = _load_coverage_missing_lines(report_path, project_root)
    report_path.unlink(missing_ok=True)

    candidates = _collect_candidates(
        project_root,
        missing_by_file,
        min_uncovered_ratio=args.min_uncovered_ratio,
    )
    return _report_or_generate(args, project_root, _select_target(candidates, args.target_function))


def _report_or_generate(args: argparse.Namespace, project_root: Path, candidates: list[FunctionCandidate]) -> int:
    if args.mode == MODE_REPORT:
        _print_report(candidates)
        return EXIT_PASSED

    if not candidates:
        print("No candidate function found for generation.")
        return EXIT_PASSED

    manifest = _load_manifest(project_root)
    pool = LocalLlmPool(wrapper_llm_settings(args))
    try:
        return _run_generation(args, project_root, candidates, manifest, pool)
    except LocalLlmUnavailable as exc:
        print_stderr(f"Error: {exc}")
        return EXIT_NO_MODEL


def _run_generation(
    args: argparse.Namespace,
    project_root: Path,
    candidates: list[FunctionCandidate],
    manifest: dict[str, object],
    pool: LocalLlmPool,
) -> int:
    """Run generate or generate-all mode. Raises LocalLlmUnavailable when no server can answer."""
    if args.mode == "generate":
        if args.target_function is not None and len(candidates) > 1:
            print(
                f"Ambiguous target function '{args.target_function}' matched "
                f"{len(candidates)} candidates:",
                file=sys.stderr,
            )
            for candidate in candidates:
                print(f" - {_format_candidate_ref(candidate)}", file=sys.stderr)
            print(
                "Use a qualified target such as Class.method, module.function, "
                "or the full candidate id from report mode.",
                file=sys.stderr,
            )
            return 1
        result = _try_generate_for_candidate(
            project_root,
            candidates[0],
            manifest,
            max_retries=args.max_retries,
            max_prompt_tokens=args.max_prompt_tokens,
            verbose_prompts=args.verbose_prompts,
            pool=pool,
        )
        if result.success:
            print(
                f"Generated: {result.generated_file} for {result.candidate.id}"
            )
            if result.generated_file is not None:
                _print_added_tests(
                    [AddedTest(path=result.generated_file, candidate=result.candidate)]
                )
            return 0
        if _is_skipped_result(result):
            print(f"Skipped: {result.candidate.id} - {result.detail}")
            _print_added_tests([])
            return 0
        print(f"Failed: {result.candidate.id} - {result.detail}", file=sys.stderr)
        return 1

    # generate-all
    success_count = 0
    failed_count = 0
    skipped_count = 0
    added_tests: list[AddedTest] = []
    for candidate in candidates:
        result = _try_generate_for_candidate(
            project_root,
            candidate,
            manifest,
            max_retries=args.max_retries,
            max_prompt_tokens=args.max_prompt_tokens,
            verbose_prompts=args.verbose_prompts,
            pool=pool,
        )
        if result.success:
            success_count += 1
            print(f"[OK] {result.generated_file}")
            if result.generated_file is not None:
                added_tests.append(
                    AddedTest(path=result.generated_file, candidate=result.candidate)
                )
        elif _is_skipped_result(result):
            skipped_count += 1
            print(f"[SKIP] {candidate.id} - {result.detail}")
        else:
            failed_count += 1
            print(f"[FAIL] {candidate.id} - {result.detail}")

    _print_added_tests(added_tests)
    print(
        f"Summary: generated={success_count}, skipped={skipped_count}, "
        f"failed={failed_count}, total={len(candidates)}"
    )
    return 0 if failed_count == 0 else 1


def resolved_mode(args: argparse.Namespace) -> str:
    """``--mode``, unless ``--generate`` or ``--generate-all`` (its shortcuts) names the mode instead."""
    if args.generate:
        return MODE_GENERATE
    if args.generate_all:
        return MODE_GENERATE_ALL
    return args.mode


def _announcer(mode: str, numbered: bool) -> ProjectAnnouncer:
    """The line introducing a project: ``[<i>/<n>] `` before it when *numbered* (``--verbose-output``)."""

    def announce(index: int, total: int, project: str) -> None:
        prefix = f"[{index}/{total}] " if numbered else ""
        print(f"{prefix}Running test-gen for {project} (mode={mode})")

    return announce


def _run_and_report(args: argparse.Namespace, project_root: Path) -> int:
    """*project_root*'s run followed by its ``[PASS]`` / ``[FAIL]`` line."""
    code = run_project(args, project_root)
    if code == EXIT_PASSED:
        print(f"[PASS] {project_root.name}")
    else:
        print(f"[FAIL] {project_root.name} (exit code: {code})")
    return code


def run_test_gen(args: argparse.Namespace, workspace: Path) -> int:
    """The wrapper's run over *workspace*: refuse both mode shortcuts at once, select, run each project,
    summarize."""
    if args.generate and args.generate_all:
        print(BOTH_GENERATE_SWITCHES)
        return EXIT_FAILED
    args.mode = resolved_mode(args)
    try:
        projects = select_projects(args, workspace, usage=USAGE_LINES, wording=WORDING)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    line_buffered_stdout()
    results = run_projects(
        projects,
        lambda project: _run_and_report(args, workspace / project),
        stop_on_error=args.stop_on_error,
        stop_message=STOP_MESSAGE,
        announce=_announcer(args.mode, numbered=args.verbose_output),
    )
    return print_summary(SUMMARY_TITLE, results, separator=_SUMMARY_SEPARATOR)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/test-gen.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Coverage-driven test generation for Datrix projects.", allow_abbrev=False
    )
    add_project_arguments(parser)
    parser.add_argument("--mode", choices=MODES, default=MODE_REPORT, help="report | generate | generate-all")
    parser.add_argument("--generate", action="store_true", help=f"Shortcut for --mode {MODE_GENERATE}.")
    parser.add_argument("--generate-all", action="store_true", help=f"Shortcut for --mode {MODE_GENERATE_ALL}.")
    parser.add_argument(
        "--target-function", type=str, default=None, help="Optional function name to target (for generate mode)."
    )
    parser.add_argument(
        "--max-retries", type=int, default=DEFAULT_MAX_RETRIES, metavar="N",
        help=f"Maximum retries per generation attempt (default: {DEFAULT_MAX_RETRIES}).",
    )
    parser.add_argument(
        "--min-uncovered-ratio", type=float, default=DEFAULT_UNCOVERED_RATIO, metavar="R",
        help=f"Minimum uncovered ratio to include a function (default: {DEFAULT_UNCOVERED_RATIO}).",
    )
    parser.add_argument(
        "--max-prompt-tokens", type=int, default=DEFAULT_MAX_PROMPT_TOKENS, metavar="N",
        help=f"Warn when generated prompts exceed this approximate token budget (default: {DEFAULT_MAX_PROMPT_TOKENS}).",
    )
    parser.add_argument("--verbose-prompts", action="store_true", help="Print generated prompts for debugging.")
    add_wrapper_llm_arguments(parser, timeout_seconds=DEFAULT_LLM_TIMEOUT_SECONDS, model_flag="--model")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop after the first project failure.")
    parser.add_argument("--verbose-output", action="store_true", help="Number the per-project lines.")
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the self-test (no test is run, no model is asked)."
    )
    parser.set_defaults(debug=False)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_test_gen(args, WORKSPACE_DIR)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_MISSING_PROJECT: Final = "no-such-project"
_PLANTED_SRC_ONLY: Final = "datrix-b"
_PLANTED_MODULE: Final = '''"""A planted module."""


def covered(value: int) -> int:
    return value + 1


def uncovered(value: int) -> int:
    if value > 0:
        return value * 2
    return -value
'''
# ``uncovered`` spans lines 8-11 of the planted module; 9-11 are missing, 3 of 4 lines (0.75).
_UNCOVERED_LINES: Final = (9, 10, 11)


def _report(argv: Sequence[str], workspace: Path | None = None) -> tuple[int, str, str]:
    """Exit code, stdout and stderr of a run (forms that stop before pytest) over *workspace*, or over a
    planted one (``datrix-a`` with src/ and tests/, ``datrix-b`` with src/ only, the showcase)."""
    out, err = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as raw:
        root = workspace if workspace is not None else plant_workspace(Path(raw))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_test_gen(build_parser().parse_args(list(argv)), root)
    return code, out.getvalue(), err.getvalue()


def _check_both_generate_switches_are_refused_before_selection() -> None:
    for argv in (["datrix-a", "--generate", "--generate-all"], ["--generate", "--generate-all"]):
        code, out, _ = _report(argv)
        assert (code, out.splitlines()) == (EXIT_FAILED, [BOTH_GENERATE_SWITCHES]), (argv, code, out)


def _check_mode_shortcuts_name_the_mode() -> None:
    parser = build_parser()
    cases = {
        (): MODE_REPORT,
        ("--mode", MODE_GENERATE_ALL): MODE_GENERATE_ALL,
        ("--generate",): MODE_GENERATE,
        ("--mode", MODE_GENERATE, "--generate-all"): MODE_GENERATE_ALL,
    }
    for argv, expected in cases.items():
        assert resolved_mode(parser.parse_args(list(argv))) == expected, (argv, expected)


def _check_refusals_print_the_wrapper_lines() -> None:
    code, out, _ = _report([SHOWCASE])
    assert (code, out.splitlines()) == (EXIT_FAILED, [WORDING.none_valid]), (code, out)
    code, out, _ = _report([])
    assert (code, out.splitlines()) == (EXIT_FAILED, [*WORDING.none_given_heading, *USAGE_LINES]), (code, out)
    with tempfile.TemporaryDirectory() as raw:
        empty = Path(raw)
        code, out, _ = _report(["--all"], empty)
    assert (code, out.splitlines()) == (EXIT_FAILED, [WORDING.none_found.format(workspace=empty)]), (code, out)


def _check_missing_src_tests_or_root_fail_before_pytest() -> None:
    code, out, err = _report([_PLANTED_SRC_ONLY, _MISSING_PROJECT, "--verbose-output"])
    expected = [
        f"[1/2] Running test-gen for {_PLANTED_SRC_ONLY} (mode={MODE_REPORT})",
        f"[FAIL] {_PLANTED_SRC_ONLY} (exit code: 1)",
        f"[2/2] Running test-gen for {_MISSING_PROJECT} (mode={MODE_REPORT})",
        f"[FAIL] {_MISSING_PROJECT} (exit code: 1)",
        "",
        SUMMARY_TITLE,
        f" [FAIL] {_PLANTED_SRC_ONLY}",
        f" [FAIL] {_MISSING_PROJECT}",
    ]
    assert (code, out.splitlines()) == (EXIT_FAILED, expected), (code, out)
    assert "Error: project root must contain src/ and tests/ directories." in err, err
    assert "Error: project root is not a directory:" in err, err
    code, out, _ = _report([_MISSING_PROJECT, _PLANTED_SRC_ONLY, "--generate", "--stop-on-error"])
    expected_stopped = [
        f"Running test-gen for {_MISSING_PROJECT} (mode={MODE_GENERATE})",
        f"[FAIL] {_MISSING_PROJECT} (exit code: 1)",
        STOP_MESSAGE,
        "",
        SUMMARY_TITLE,
        f" [FAIL] {_MISSING_PROJECT}",
    ]
    assert (code, out.splitlines()) == (EXIT_FAILED, expected_stopped), (code, out)


def _check_coverage_report_ranks_the_uncovered_functions() -> None:
    with tempfile.TemporaryDirectory() as raw:
        project_root = (Path(raw) / "datrix-a").resolve()
        module = project_root / PackageMarker.SRC.value / "pkg" / "mod.py"
        module.parent.mkdir(parents=True)
        module.write_text(_PLANTED_MODULE, encoding="utf-8")
        report_path = project_root / "coverage.json"
        files = {"src/pkg/mod.py": {"missing_lines": list(_UNCOVERED_LINES)}}
        report_path.write_text(json.dumps({"files": files}), encoding="utf-8")
        missing = _load_coverage_missing_lines(report_path, project_root)
        candidates = _collect_candidates(project_root, missing, min_uncovered_ratio=DEFAULT_UNCOVERED_RATIO)
        assert [(c.module_path, c.function_name) for c in candidates] == [("pkg.mod", "uncovered")], candidates
        assert candidates[0].uncovered_ratio == 0.75, candidates[0]
        assert _select_target(candidates, "pkg.mod.uncovered") == candidates, "a qualified target must match"
        assert _select_target(candidates, "covered") == [], "a covered function is never a candidate"
        args = build_parser().parse_args([])
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = _report_or_generate(args, project_root, candidates)
    lines = printed.getvalue().splitlines()
    assert code == EXIT_PASSED and lines[0] == "Ranked uncovered functions:", (code, lines)
    assert lines[1].startswith("001. ") and lines[1].endswith(":8 uncovered"), lines


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_both_generate_switches_are_refused_before_selection,
    _check_mode_shortcuts_name_the_mode,
    _check_refusals_print_the_wrapper_lines,
    _check_missing_src_tests_or_root_fail_before_pytest,
    _check_coverage_report_ranks_the_uncovered_functions,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())

