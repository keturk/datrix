#!/usr/bin/env python3
"""Coverage-driven unit test generation for Datrix projects using Ollama.

Modes:
- report: list uncovered functions ranked by priority
- generate: generate test for top-ranked function (or --target-function)
- generate-all: attempt test generation for every ranked function
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Add library root to sys.path for shared imports
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

_ollama_utils = importlib.import_module("shared.ollama_utils")
OLLAMA_DEFAULT_MODEL = str(_ollama_utils.OLLAMA_DEFAULT_MODEL)
OLLAMA_DEFAULT_URL = str(_ollama_utils.OLLAMA_DEFAULT_URL)
call_ollama = _ollama_utils.call_ollama
parse_ollama_response = _ollama_utils.parse_ollama_response

DEFAULT_UNCOVERED_RATIO = 0.5
DEFAULT_MAX_RETRIES = 3
MANIFEST_VERSION = 1

SYSTEM_PROMPT = """You are a Python test expert for the Datrix project.

Test rules (MANDATORY):
- Use pytest (no unittest)
- Use REAL objects only - NO unittest.mock, NO MagicMock, NO patch, NO SimpleNamespace
- Use factories from datrix_common.testing when available
- Use .dtrx fixture files for parser/transformer tests
- Validate generated code with ast.parse() or yaml.safe_load()
- Test naming: test_<function_name>_<scenario>
- Structure: Arrange -> Act -> Assert
- Add @pytest.mark.unit decorator
- Import the function under test from its actual module path

Output rules:
- Return ONLY a complete Python test file inside a ```python code fence
- Do not include prose before or after the code fence
- Use ASCII characters only
- Include all necessary imports at the top
- One test function per scenario (2-4 scenarios per function)
- Test both happy path and error cases
- Do not duplicate scenarios already covered by the existing tests in the prompt
- Do not reuse any forbidden existing test function name listed in the prompt
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


def _coverage_source(project_root: Path) -> str:
    if (project_root / "src" / "datrix").exists():
        return "src/datrix"
    return "src"


def _run_coverage_json(project_root: Path, report_path: Path) -> tuple[bool, str]:
    coverage_source = _coverage_source(project_root)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        f"--cov={coverage_source}",
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


def _manifest_path(project_root: Path) -> Path:
    return project_root / ".generated" / "test-gen-manifest.json"


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


def _extract_import_lines(source_lines: list[str]) -> str:
    imports: list[str] = []
    for line in source_lines:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(line)
        elif imports and stripped and not stripped.startswith("#"):
            break
    return "\n".join(imports[:120])


def _extract_class_context(
    tree: ast.Module,
    source_lines: list[str],
    class_name: str | None,
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
            methods_text = ", ".join(method_names[:25])
            return f"{header}\nMethods: {methods_text}"
    return ""


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

    related: list[Path] = []
    direct = project_root / "tests" / "unit" / f"test_{module_stem}.py"
    if direct.exists():
        related.append(direct)

    for test_file in _iter_test_files(project_root):
        if test_file in related:
            continue
        if module_stem in test_file.stem:
            related.append(test_file)
            continue
        text = test_file.read_text(encoding="utf-8", errors="replace")
        if any(term in text for term in search_terms):
            related.append(test_file)
    return related


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
            names = "\n".join(f"- {name}" for name in test_names)
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


def _build_user_prompt(project_root: Path, candidate: FunctionCandidate) -> str:
    source_text = candidate.file_path.read_text(encoding="utf-8", errors="replace")
    source_lines = source_text.splitlines()
    tree = ast.parse(source_text)

    function_source = _extract_source_segment(
        source_lines,
        candidate.start_line,
        candidate.end_line,
    )
    imports_text = _extract_import_lines(source_lines)
    class_context = _extract_class_context(tree, source_lines, candidate.class_name)
    existing_test_context = _build_existing_test_context(project_root, candidate)
    existing_test_names = "\n".join(
        f"- {name}" for name in sorted(_collect_existing_test_function_names(project_root))
    )

    import_line = (
        f"from {candidate.module_path} import {candidate.function_name}"
        if candidate.class_name is None
        else f"from {candidate.module_path} import {candidate.class_name}"
    )

    return (
        f"Target function: {candidate.id}\n\n"
        f"Module import path:\n{import_line}\n\n"
        "Function source:\n"
        f"```python\n{function_source}\n```\n\n"
        "Class context (if method):\n"
        f"```python\n{class_context or '# none'}\n```\n\n"
        "File imports:\n"
        f"```python\n{imports_text}\n```\n\n"
        "Forbidden existing test function names (do not use these names):\n"
        f"{existing_test_names or '- none'}\n\n"
        "Existing related test summary (do not duplicate these scenarios):\n"
        f"{existing_test_context or '- none'}\n"
    )


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
    ollama_url: str,
    model: str,
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
    retry_feedback = ""

    for attempt in range(1, max_retries + 1):
        prompt = prompt_base
        if retry_feedback:
            prompt += (
                "\n\nIMPORTANT: previous attempt failed. "
                "Fix using this feedback:\n"
                f"{retry_feedback}\n"
            )

        response = call_ollama(
            SYSTEM_PROMPT,
            prompt,
            ollama_url=ollama_url,
            ollama_model=model,
        )
        if response is None:
            retry_feedback = "Ollama returned no response."
            continue

        parsed = parse_ollama_response(response)
        if parsed is None:
            retry_feedback = "Could not parse Python code fence from Ollama response."
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
                model,
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Coverage-driven test generation for Datrix projects.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Path to a Datrix package root (containing src/ and tests/).",
    )
    parser.add_argument(
        "--mode",
        choices=("report", "generate", "generate-all"),
        default="report",
        help="report | generate | generate-all",
    )
    parser.add_argument(
        "--target-function",
        type=str,
        default=None,
        help="Optional function name to target (for generate mode).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        metavar="N",
        help=f"Maximum retries per generation attempt (default: {DEFAULT_MAX_RETRIES}).",
    )
    parser.add_argument(
        "--min-uncovered-ratio",
        type=float,
        default=DEFAULT_UNCOVERED_RATIO,
        metavar="R",
        help=(
            "Minimum uncovered ratio to include a function "
            f"(default: {DEFAULT_UNCOVERED_RATIO})."
        ),
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default=OLLAMA_DEFAULT_URL,
        help=f"Ollama URL (default: {OLLAMA_DEFAULT_URL}).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=OLLAMA_DEFAULT_MODEL,
        help=f"Ollama model (default: {OLLAMA_DEFAULT_MODEL}).",
    )

    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"Error: project root is not a directory: {project_root}", file=sys.stderr)
        return 1

    if not (project_root / "src").is_dir() or not (project_root / "tests").is_dir():
        print(
            "Error: project root must contain src/ and tests/ directories.",
            file=sys.stderr,
        )
        return 1

    report_path = project_root / ".coverage_test_gen.json"
    ok, err = _run_coverage_json(project_root, report_path)
    if not ok:
        print(err, file=sys.stderr)
        return 1
    if not report_path.exists():
        print("Coverage JSON report was not produced by pytest-cov.", file=sys.stderr)
        return 1

    missing_by_file = _load_coverage_missing_lines(report_path, project_root)
    report_path.unlink(missing_ok=True)

    candidates = _collect_candidates(
        project_root,
        missing_by_file,
        min_uncovered_ratio=args.min_uncovered_ratio,
    )
    candidates = _select_target(candidates, args.target_function)

    if args.mode == "report":
        _print_report(candidates)
        return 0

    if not candidates:
        print("No candidate function found for generation.")
        return 0

    manifest = _load_manifest(project_root)

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
            ollama_url=args.ollama_url,
            model=args.model,
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
            ollama_url=args.ollama_url,
            model=args.model,
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


if __name__ == "__main__":
    sys.exit(main())

