#!/usr/bin/env python3
"""
Run Radon metrics on a Datrix project's src tree.

Modes:
    check - Enforce max cyclomatic and cognitive complexity; exit 1 if any block exceeds --max.
    cc - Report cyclomatic complexity (McCabe) per block.
    raw - Report raw metrics (SLOC, comment/blank lines, LOC, LLOC) per file.
    halstead - Report Halstead metrics (volume, difficulty, etc.) per file.
    mi - Report Maintainability Index per file.

Only analyzes Python files under project_root/src; tests are excluded by default.
In mode=check, both cyclomatic complexity (Radon) and cognitive complexity
(via cognitive_complexity) are enforced.

Usage:
    python complexity.py --project-root D:\\datrix\\datrix-common --mode check --max 15
    python complexity.py --project-root D:\\datrix\\datrix-common --mode raw
    python complexity.py --project-root . --mode halstead --verbose
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from radon.complexity import cc_visit
    from radon.raw import analyze as raw_analyze
    from radon.metrics import h_visit, mi_visit
except ImportError:
    print(
    "Error: radon is not installed. Install with: pip install radon>=6.0",
    file=sys.stderr,
    )
    sys.exit(2)

try:
    from cognitive_complexity.api import get_cognitive_complexity
except ImportError:
    get_cognitive_complexity = None # type: ignore[assignment, misc]

DEFAULT_MAX_COMPLEXITY = 15
DEFAULT_IGNORE_DIRS = ("tests", "test", "__pycache__", ".git")

# Blocks excluded from cognitive check (path_substring, function_name).
EXCLUDED_COGNITIVE_BLOCKS: list[tuple[str, str]] = [
    ("datrix_codegen_python/generators/event_generator.py", "_build_handlers_context"),
    ("datrix_codegen_python/generators/event_generator.py", "_build_event_schemas_context"),
    ("datrix_codegen_python/generators/model_generator.py", "_build_model_context"),
    ("datrix_codegen_python/generators/route_generator.py", "_add_imports_from_route_context"),
    ("datrix_codegen_python/transpiler/python_transpiler.py", "visit_call"),
    ("datrix_codegen_python/transpiler/python_transpiler.py", "visit_for_loop"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "_get_dto_fields"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "_map_type_to_validators"),
    ("datrix_codegen_typescript/generators/entity_generator.py", "_map_relationship"),
    # datrix-language cognitive
    ("datrix_language/datrix_model/base.py", "collect_refs"),
    ("datrix_language/parser/", "_merge_applications"),
    ("datrix_language/semantic/field_types.py", "visit_type"),
    ("datrix_language/semantic/imports.py", "_process_import_directive"),
    ("datrix_language/semantic/references.py", "_resolve_index_fields"),
    ("datrix_language/semantic/symbols.py", "_register_block_entities"),
    ("datrix_language/semantic/type_walker.py", "_apply_visitor"),
    ("datrix_language/semantic/type_checker.py", "visit_type"),
    ("datrix_language/semantic/type_walker.py", "_walk_service"),
    ("datrix_language/semantic/type_walker.py", "_walk_body"),
    ("datrix_language/transformers/transformer.py", "transform"),
    ("datrix_language/semantic/validators/cross_service.py", "_check_xsv001"),
    ("datrix_language/semantic/validators/entity.py", "_check_ent003"),
    ("datrix_language/semantic/validators/event.py", "_check_evt004"),
    ("datrix_language/semantic/validators/relationship.py", "_iter_relationships"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_call_expression"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_string_literal"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_lambda_expression"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_fstring"),
    ("datrix_language/transformers/statement_transformer.py", "_transform_try_statement"),
    ("datrix_language/transformers/transformer.py", "_transform_import_statement"),
    ("datrix_language/transformers/transformer.py", "_transform_system_block"),
    ("datrix_language/transformers/transformer.py", "_transform_service_block"),
    ("datrix_language/transformers/transformer.py", "_transform_index_declaration"),
    ("datrix_language/transformers/transformer.py", "_transform_entity_declaration"),
    ("datrix_language/transformers/transformer.py", "_transform_cache_entry"),
    ("datrix_language/transformers/transformer.py", "_transform_rest_api_block"),
    ("datrix_language/transformers/transformer.py", "_transform_endpoint_declaration"),
    ("datrix_language/transformers/transformer.py", "_transform_resource_declaration"),
    ("datrix_language/transformers/transformer.py", "_transform_batch_declaration"),
    ("datrix_language/transformers/transformer.py", "_transform_graphql_member"),
    ("datrix_language/transformers/transformer.py", "_transform_job_declaration"),
    ("datrix_language/types/parser.py", "_parse_int_list"),
    ("datrix_language/types/parser.py", "_parse_type_expr_inner"),
]

# Blocks excluded from cyclomatic check (e.g. ABCs with many abstract method stubs).
# Each entry: (path_substring, block_name). Block is skipped if path contains substring and name matches.
EXCLUDED_CYCLOMATIC_BLOCKS: list[tuple[str, str]] = [
    ("datrix_common/generator.py", "Generator"),
    ("transpiler/base.py", "Transpiler"),
    ("datrix_codegen_python/transpiler/python_transpiler.py", "PythonTranspiler"),
    ("datrix_codegen_typescript/transpiler/ts_transpiler.py", "TypeScriptTranspiler"),
    ("datrix_codegen_python/generators/api_test_generator.py", "ApiTestGenerator"),
    ("datrix_codegen_python/generators/cache_generator.py", "CacheGenerator"),
    ("datrix_codegen_python/generators/cqrs_generator.py", "CqrsGenerator"),
    ("datrix_codegen_python/generators/doc_generator.py", "DocGenerator"),
    ("datrix_codegen_python/generators/event_generator.py", "EventGenerator"),
    ("datrix_codegen_python/generators/entity_test_generator.py", "EntityTestGenerator"),
    ("datrix_codegen_python/generators/model_generator.py", "ModelGenerator"),
    ("datrix_codegen_python/generators/project_generator.py", "ProjectGenerator"),
    ("datrix_codegen_python/generators/route_generator.py", "RouteGenerator"),
    ("datrix_codegen_python/generators/schema_generator.py", "SchemaGenerator"),
    ("datrix_codegen_python/generators/integration_generator.py", "IntegrationGenerator"),
    ("datrix_codegen_python/generators/jobs_generator.py", "JobsGenerator"),
    ("datrix_codegen_python/generators/nosql_connection_generator.py", "NosqlConnectionGenerator"),
    ("datrix_codegen_python/generators/observability_generator.py", "ObservabilityGenerator"),
    ("datrix_codegen_python/generators/pubsub_generator.py", "PubsubGenerator"),
    ("datrix_codegen_python/generators/rdbms_connection_generator.py", "RdbmsConnectionGenerator"),
    ("datrix_codegen_python/generators/resilience_generator.py", "ResilienceGenerator"),
    ("datrix_codegen_python/generators/service_generator.py", "ServiceGenerator"),
    ("datrix_codegen_python/generators/test_factory_generator.py", "TestFactoryGenerator"),
    ("datrix_codegen_typescript/generators/controller_generator.py", "ControllerGenerator"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "DtoGenerator"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "_map_type_to_validators"),
    ("datrix_codegen_typescript/generators/entity_generator.py", "EntityGenerator"),
    ("datrix_codegen_typescript/generators/project_generator.py", "ProjectGenerator"),
    ("datrix_codegen_typescript/plugin.py", "TypeScriptGenerator"),
    # datrix-language: model/parser/semantic/transformer classes and key methods
    ("datrix_language/datrix_model/api.py", "RestApi"),
    ("datrix_language/datrix_model/base.py", "Node"),
    ("datrix_language/datrix_model/base.py", "TypeContainer"),
    ("datrix_language/datrix_model/blocks.py", "RdbmsBlock"),
    ("datrix_language/datrix_model/blocks.py", "NosqlBlock"),
    ("datrix_language/datrix_model/callables.py", "Endpoint"),
    ("datrix_language/datrix_model/containers.py", "Application"),
    ("datrix_language/datrix_model/containers.py", "Service"),
    ("datrix_language/datrix_model/entity.py", "Entity"),
    ("datrix_language/parser/", "TreeSitterParser"),
    ("datrix_language/semantic/field_types.py", "_RefResolver"),
    ("datrix_language/semantic/type_checker.py", "_TypeValidator"),
    ("datrix_language/semantic/type_checker.py", "visit_type"),
    ("datrix_language/semantic/type_walker.py", "_walk_service"),
    ("datrix_language/semantic/type_walker.py", "_walk_body"),
    ("datrix_language/semantic/validators/api.py", "ApiValidator"),
    ("datrix_language/semantic/validators/cqrs.py", "CqrsValidator"),
    ("datrix_language/semantic/validators/cross_service.py", "CrossServiceValidator"),
    ("datrix_language/semantic/validators/entity.py", "EntityValidator"),
    ("datrix_language/semantic/validators/event.py", "EventValidator"),
    ("datrix_language/semantic/validators/relationship.py", "RelationshipValidator"),
    ("datrix_language/semantic/validators/service.py", "ServiceValidator"),
    ("datrix_language/transformers/api_transformer.py", "ApiTransformer"),
    ("datrix_language/transformers/block_transformer.py", "BlockTransformer"),
    ("datrix_language/transformers/cqrs_transformer.py", "CqrsTransformer"),
    ("datrix_language/transformers/entity_transformer.py", "EntityTransformer"),
    ("datrix_language/transformers/expression_transformer.py", "ExpressionTransformer"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_lambda_expression"),
    ("datrix_language/transformers/statement_transformer.py", "StatementTransformer"),
    ("datrix_language/transformers/transformer.py", "ASTTransformer"),
    ("datrix_language/transformers/transformer.py", "transform"),
    ("datrix_language/transformers/transformer.py", "_transform_system_block"),
    ("datrix_language/transformers/transformer.py", "_transform_service_block"),
    ("datrix_language/transformers/transformer.py", "_transform_cache_entry"),
    ("datrix_language/transformers/transformer.py", "_transform_endpoint_declaration"),
    ("datrix_language/transformers/transformer.py", "_transform_resource_declaration"),
    ("datrix_language/transformers/transformer.py", "_transform_batch_declaration"),
    ("datrix_language/transformers/transformer.py", "_transform_graphql_member"),
    ("datrix_language/transformers/type_transformer.py", "TypeTransformer"),
    ("datrix_language/types/parser.py", "_parse_int_list"),
    ("datrix_language/types/parser.py", "_parse_type_expr_inner"),
    ("datrix_language/types/registry.py", "TypeRegistry"),
]

OLLAMA_DEFAULT_URL = "http://10.94.0.100:11434"
OLLAMA_DEFAULT_MODEL = "qwen3-coder:30b"
OLLAMA_TIMEOUT_SECONDS = 300


def get_block_complexity(block: object) -> int | None:
    """Return cyclomatic complexity for a radon Function or Class block."""
    if hasattr(block, "real_complexity"):
        return getattr(block, "real_complexity")
    if hasattr(block, "complexity"):
        return getattr(block, "complexity")
    return None


def collect_py_files(
    project_root: Path,
    ignore_dirs: tuple[str, ...],
    ignore_path_contains_all: tuple[str, ...] | None = None,
) -> list[Path]:
    """Return sorted list of Python files under project_root/src.

    Excludes paths that contain any of ignore_dirs, or that contain all
    segment names in ignore_path_contains_all (e.g. ("builtins", "objects")).
    """
    src = project_root / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    for py_path in src.rglob("*.py"):
        parts = py_path.relative_to(src).parts
        if any(part in ignore_dirs for part in parts):
            continue
        if ignore_path_contains_all and all(
            seg in parts for seg in ignore_path_contains_all
        ):
            continue
        out.append(py_path)
    return sorted(out)


def run_check(
    project_root: Path,
    max_complexity: int,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None = None,
) -> list[tuple[str, str, int, int]]:
    """Check that no block exceeds max complexity. Return list of violations."""
    violations: list[tuple[str, str, int, int]] = []
    for file_path in collect_py_files(
        project_root, ignore_dirs, ignore_path_contains_all
    ):
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            if verbose:
                print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue
        try:
            blocks = cc_visit(source)
        except Exception as e:
            if verbose:
                print(f"Warning: radon failed on {file_path}: {e}", file=sys.stderr)
            continue
        rel_path = str(file_path)
        rel_path_norm = rel_path.replace("\\", "/")
        for block in blocks:
            complexity = get_block_complexity(block)
            if complexity is None or complexity <= max_complexity:
                continue
            name = getattr(block, "name", "?")
            if any(
                path_part in rel_path_norm and name == block_name
                for path_part, block_name in EXCLUDED_CYCLOMATIC_BLOCKS
            ):
                continue
            lineno = getattr(block, "lineno", 0)
            violations.append((rel_path, name, lineno, complexity))
    return violations


def run_check_cognitive(
    project_root: Path,
    max_complexity: int,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None = None,
) -> list[tuple[str, str, int, int]]:
    """Check that no function exceeds max cognitive complexity. Return list of violations."""
    if get_cognitive_complexity is None:
        raise RuntimeError(
            "cognitive_complexity is not installed. Install with: pip install cognitive_complexity"
        )
    violations: list[tuple[str, str, int, int]] = []
    for file_path in collect_py_files(
        project_root, ignore_dirs, ignore_path_contains_all
    ):
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            if verbose:
                print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            if verbose:
                print(f"Warning: could not parse {file_path}: {e}", file=sys.stderr)
            continue
        rel_path = str(file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                try:
                    complexity = get_cognitive_complexity(node)
                except Exception as e:
                    if verbose:
                        print(
                            f"Warning: cognitive_complexity failed on {file_path} {node.name}: {e}",
                            file=sys.stderr,
                        )
                    continue
                if complexity <= max_complexity:
                    continue
                rel_path_norm = rel_path.replace("\\", "/")
                if any(
                    path_part in rel_path_norm and node.name == func_name
                    for path_part, func_name in EXCLUDED_COGNITIVE_BLOCKS
                ):
                    continue
                violations.append(
                    (rel_path, node.name, node.lineno, complexity)
                )
    return violations


def find_function_node(
    source: str, func_name: str, lineno: int,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Find the AST function/method node matching name and line number."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name and node.lineno == lineno:
                return node
    return None


def get_function_line_range(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[int, int]:
    """Return (start_line, end_line) 1-indexed, inclusive of decorators."""
    start = node.lineno
    if node.decorator_list:
        start = min(d.lineno for d in node.decorator_list)
    assert node.end_lineno is not None
    return start, node.end_lineno


def normalize_indentation(source: str, target_indent: str) -> str:
    """Re-indent source so its base indentation matches target_indent."""
    lines = source.splitlines(keepends=True)
    if not lines:
        return source
    # Detect current base indentation from first non-empty line
    current_indent = ""
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            current_indent = line[: len(line) - len(stripped)]
            break
    if current_indent == target_indent:
        return source
    result: list[str] = []
    for line in lines:
        if not line.strip():
            result.append(line)
        elif line.startswith(current_indent):
            result.append(target_indent + line[len(current_indent) :])
        else:
            result.append(line)
    return "".join(result)


def parse_ollama_response(text: str) -> str:
    """Extract Python code from Ollama response, stripping think tags and code fences."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    code_match = re.search(r"```(?:python)?\s*\n(.*?)```", cleaned, flags=re.DOTALL)
    if code_match:
        return code_match.group(1)
    return cleaned


def call_ollama(
    function_source: str,
    func_name: str,
    complexity_type: str,
    complexity_value: int,
    max_complexity: int,
    ollama_url: str,
    model: str,
) -> str:
    """Send function to Ollama for complexity reduction. Return fixed source."""
    indent_count = 0
    for line in function_source.splitlines():
        stripped = line.lstrip()
        if stripped:
            indent_count = len(line) - len(stripped)
            break

    prompt = (
        f"Refactor this Python function to reduce its {complexity_type} complexity "
        f"from {complexity_value} to at most {max_complexity}.\n\n"
        f"Rules:\n"
        f"- Keep the same function signature, behavior, and indentation ({indent_count} spaces)\n"
        f"- You may extract helper functions/methods at the same indent level, "
        f"placed before the main function\n"
        f"- Return ONLY Python code, no explanations\n\n"
        f"```python\n{function_source}```"
    )

    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 8192},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Failed to connect to Ollama at {ollama_url}: {e}"
        ) from e
    except TimeoutError as exc:
        raise RuntimeError(
            f"Ollama request timed out after {OLLAMA_TIMEOUT_SECONDS}s"
        ) from exc

    content = data["message"]["content"]
    return parse_ollama_response(content)


def _run_ruff_check(file_path: Path, verbose: bool) -> bool:
    """Run ruff check for undefined names on the file. Return True if clean."""
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "F821", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        if verbose:
            print(
                "Warning: ruff not found, skipping undefined name check",
                file=sys.stderr,
            )
        return True
    except subprocess.TimeoutExpired:
        print("Warning: ruff check timed out", file=sys.stderr)
        return True
    if result.returncode != 0:
        print("Ruff found undefined names:", file=sys.stderr)
        for line in result.stdout.strip().splitlines():
            print(f"  {line}", file=sys.stderr)
        return False
    return True


PYTEST_TIMEOUT_SECONDS = 600


def _run_pytest(project_root: Path, verbose: bool) -> bool:
    """Run pytest with fail-fast on the project. Return True if all pass."""
    print("Running tests (pytest -x -q --tb=short)...", file=sys.stderr)
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-x", "-q", "--tb=short"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        print("Warning: pytest not found, skipping tests", file=sys.stderr)
        return True
    except subprocess.TimeoutExpired:
        print(
            f"Warning: tests timed out after {PYTEST_TIMEOUT_SECONDS}s",
            file=sys.stderr,
        )
        return False
    if result.returncode != 0:
        print("Tests failed:", file=sys.stderr)
        output_lines = result.stdout.strip().splitlines()
        tail = output_lines[-20:] if len(output_lines) > 20 else output_lines
        for line in tail:
            print(f"  {line}", file=sys.stderr)
        return False
    passed_line = [l for l in result.stdout.strip().splitlines() if "passed" in l]
    if passed_line:
        print(f"  {passed_line[-1]}", file=sys.stderr)
    return True


def run_fix(
    project_root: Path,
    max_complexity: int,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None,
    ollama_url: str,
    model: str,
    run_tests: bool = False,
) -> int:
    """Fix the worst complexity violation using Ollama. Return exit code.

    Tries violations from worst to least complex. On any failure (Ollama error,
    syntax error, ruff undefined-name check, or test failure), reverts the file
    and moves to the next violation. Exits after the first successful fix.
    """
    cc_violations = run_check(
        project_root, max_complexity, ignore_dirs, verbose, ignore_path_contains_all
    )
    cog_violations: list[tuple[str, str, int, int]] = []
    if get_cognitive_complexity is not None:
        try:
            cog_violations = run_check_cognitive(
                project_root, max_complexity, ignore_dirs, verbose,
                ignore_path_contains_all,
            )
        except RuntimeError as e:
            print(str(e), file=sys.stderr)

    # Combine violations with their type
    all_violations: list[tuple[str, str, int, int, str]] = []
    for path, name, lineno, compl in cc_violations:
        all_violations.append((path, name, lineno, compl, "cyclomatic"))
    for path, name, lineno, compl in cog_violations:
        all_violations.append((path, name, lineno, compl, "cognitive"))

    if not all_violations:
        print("No complexity violations found. Nothing to fix.", file=sys.stderr)
        return 0

    # Sort by complexity descending (worst first)
    all_violations.sort(key=lambda v: v[3], reverse=True)

    # Deduplicate: same function may appear in both cyclomatic and cognitive lists
    seen: set[tuple[str, str, int]] = set()
    unique: list[tuple[str, str, int, int, str]] = []
    for v in all_violations:
        key = (v[0], v[1], v[2])
        if key not in seen:
            seen.add(key)
            unique.append(v)

    fixes_attempted = 0
    for file_path_str, func_name, lineno, complexity, comp_type in unique:
        file_path = Path(file_path_str)
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue

        node = find_function_node(source, func_name, lineno)
        if node is None:
            if verbose:
                print(
                    f"Skipping {func_name} at {file_path}:{lineno} (not a function)",
                    file=sys.stderr,
                )
            continue

        original_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        lines = source.splitlines(keepends=True)
        start, end = get_function_line_range(node)
        func_source = "".join(lines[start - 1 : end])

        print(
            f"\nFixing: {file_path}:{lineno} {func_name} "
            f"({comp_type}={complexity}, max={max_complexity})",
            file=sys.stderr,
        )
        print(
            f"Extracted function ({end - start + 1} lines, lines {start}-{end})",
            file=sys.stderr,
        )
        print(f"Sending to Ollama ({model} at {ollama_url})...", file=sys.stderr)

        try:
            fixed_source = call_ollama(
                func_source, func_name, comp_type, complexity,
                max_complexity, ollama_url, model,
            )
        except RuntimeError as e:
            print(f"Ollama error: {e}", file=sys.stderr)
            print("Trying next violation...", file=sys.stderr)
            continue

        # Normalize indentation to match original
        original_indent = ""
        for line in func_source.splitlines():
            stripped = line.lstrip()
            if stripped:
                original_indent = line[: len(line) - len(stripped)]
                break
        fixed_source = normalize_indentation(fixed_source, original_indent)

        if not fixed_source.endswith("\n"):
            fixed_source += "\n"

        # Check file hasn't been modified while Ollama was processing
        current_content = file_path.read_text(encoding="utf-8")
        current_hash = hashlib.sha256(
            current_content.encode("utf-8")
        ).hexdigest()
        if current_hash != original_hash:
            print(
                f"File {file_path} was modified during processing, skipping.",
                file=sys.stderr,
            )
            continue

        # Replace function lines and validate syntax
        new_lines = lines[: start - 1] + [fixed_source] + lines[end:]
        new_content = "".join(new_lines)

        try:
            ast.parse(new_content)
        except SyntaxError as e:
            print(f"Syntax error in Ollama output: {e}", file=sys.stderr)
            print("Trying next violation...", file=sys.stderr)
            continue

        # Write the fixed file
        file_path.write_text(new_content, encoding="utf-8")
        fixes_attempted += 1

        # Ruff check for undefined names (always)
        if not _run_ruff_check(file_path, verbose):
            print("Reverting due to ruff errors.", file=sys.stderr)
            file_path.write_text(source, encoding="utf-8")
            print("Trying next violation...\n", file=sys.stderr)
            continue

        # Pytest (opt-in with --test)
        if run_tests and not _run_pytest(project_root, verbose):
            print("Reverting due to test failures.", file=sys.stderr)
            file_path.write_text(source, encoding="utf-8")
            print("Trying next violation...\n", file=sys.stderr)
            continue

        print(f"Fixed: {file_path}:{start} {func_name}", file=sys.stderr)
        print("Re-run the script to fix more violations.", file=sys.stderr)
        return 0

    if fixes_attempted == 0:
        print("No fixable function violations found.", file=sys.stderr)
    else:
        print(
            f"Attempted {fixes_attempted} fix(es), all reverted.",
            file=sys.stderr,
        )
    return 1


def run_cc(
    project_root: Path,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
) -> None:
    """Print cyclomatic complexity per block."""
    for file_path in collect_py_files(
        project_root, ignore_dirs, ignore_path_contains_all
    ):
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            if verbose:
                print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue
        try:
            blocks = cc_visit(source)
        except Exception as e:
            if verbose:
                print(f"Warning: radon failed on {file_path}: {e}", file=sys.stderr)
            continue
        rel_path = str(file_path)
        for block in blocks:
            complexity = get_block_complexity(block)
            name = getattr(block, "name", "?")
            lineno = getattr(block, "lineno", 0)
            if complexity is not None:
                print(f"{rel_path}:{lineno} {name} (complexity={complexity})")


def run_raw(
    project_root: Path,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None = None,
) -> None:
    """Print raw metrics (SLOC, comment, blank, LOC, LLOC) per file."""
    for file_path in collect_py_files(
        project_root, ignore_dirs, ignore_path_contains_all
    ):
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            if verbose:
                print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue
        try:
            mod = raw_analyze(source)
        except Exception as e:
            if verbose:
                print(f"Warning: radon raw failed on {file_path}: {e}", file=sys.stderr)
            continue
        # loc, lloc, sloc, comments, multi, blank, single_comments
        print(
            f"{file_path} sloc={mod.sloc} lloc={mod.lloc} loc={mod.loc} "
            f"comments={mod.comments} blank={mod.blank} multi={mod.multi}"
        )


def run_halstead(
    project_root: Path,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None = None,
) -> None:
    """Print Halstead metrics (volume, difficulty, etc.) per file."""
    for file_path in collect_py_files(
        project_root, ignore_dirs, ignore_path_contains_all
    ):
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            if verbose:
                print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue
        try:
            hal = h_visit(source)
        except Exception as e:
            if verbose:
                print(
                    f"Warning: radon halstead failed on {file_path}: {e}",
                    file=sys.stderr,
                )
            continue
        t = hal.total
        print(
            f"{file_path} volume={t.volume:.1f} difficulty={t.difficulty:.1f} "
            f"effort={t.effort:.1f} h1={t.h1} h2={t.h2} N1={t.N1} N2={t.N2}"
        )


def run_mi(
    project_root: Path,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    count_multi: bool = True,
    ignore_path_contains_all: tuple[str, ...] | None = None,
) -> None:
    """Print Maintainability Index per file."""
    for file_path in collect_py_files(
        project_root, ignore_dirs, ignore_path_contains_all
    ):
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            if verbose:
                print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue
        try:
            mi = mi_visit(source, count_multi)
        except Exception as e:
            if verbose:
                print(
                    f"Warning: radon MI failed on {file_path}: {e}",
                    file=sys.stderr,
                )
            continue
        print(f"{file_path} mi={mi:.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(
    description="Radon metrics for a Datrix project (complexity, raw, Halstead, MI).",
    )
    parser.add_argument(
    "--project-root",
    type=Path,
    required=True,
    help="Path to the project root (containing src/).",
    )
    parser.add_argument(
    "--mode",
    choices=("check", "cc", "raw", "halstead", "mi"),
    default="check",
    help="Metric to run: check (enforce max), cc, raw, halstead, mi (default: check).",
    )
    parser.add_argument(
    "--max",
    type=int,
    default=DEFAULT_MAX_COMPLEXITY,
    metavar="N",
    help=f"Max cyclomatic and cognitive complexity for mode=check (default: {DEFAULT_MAX_COMPLEXITY}).",
    )
    parser.add_argument(
    "--ignore",
    type=str,
    default=",".join(DEFAULT_IGNORE_DIRS),
    help="Comma-separated directory names to ignore under src/.",
    )
    parser.add_argument(
    "--ignore-path-contains",
    type=str,
    default="",
    metavar="SEG1,SEG2",
    help="Skip files whose path contains all these segment names (e.g. builtins,objects).",
    )
    parser.add_argument(
    "--no-multi",
    action="store_true",
    help="For mode=mi: do not count multiline strings as comments.",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument(
    "--debug",
    action="store_true",
    help="Debug output (same as verbose for now).",
    )
    parser.add_argument(
    "--fix",
    action="store_true",
    help="Fix the worst complexity violation using local Ollama (mode=check only).",
    )
    parser.add_argument(
    "--ollama-url",
    type=str,
    default=OLLAMA_DEFAULT_URL,
    help=f"Ollama server URL (default: {OLLAMA_DEFAULT_URL}).",
    )
    parser.add_argument(
    "--model",
    type=str,
    default=OLLAMA_DEFAULT_MODEL,
    help=f"Ollama model name (default: {OLLAMA_DEFAULT_MODEL}).",
    )
    parser.add_argument(
    "--test",
    action="store_true",
    help="Run pytest after fix to verify; revert if tests fail (--fix only).",
    )

    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(
            f"Error: project root is not a directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    ignore_dirs = tuple(s.strip() for s in args.ignore.split(",") if s.strip())
    ignore_path_contains_all: tuple[str, ...] | None = None
    if args.ignore_path_contains:
        ignore_path_contains_all = tuple(
            s.strip() for s in args.ignore_path_contains.split(",") if s.strip()
        )
    verbose = args.verbose or args.debug

    if args.fix:
        if args.mode != "check":
            print(
                "Error: --fix can only be used with --mode check.",
                file=sys.stderr,
            )
            return 1
        return run_fix(
            project_root,
            max_complexity=args.max,
            ignore_dirs=ignore_dirs,
            verbose=verbose,
            ignore_path_contains_all=ignore_path_contains_all,
            ollama_url=args.ollama_url,
            model=args.model,
            run_tests=args.test,
        )

    if args.mode == "check":
        cc_violations = run_check(
            project_root,
            max_complexity=args.max,
            ignore_dirs=ignore_dirs,
            verbose=verbose,
            ignore_path_contains_all=ignore_path_contains_all,
        )
        try:
            cog_violations = run_check_cognitive(
                project_root,
                max_complexity=args.max,
                ignore_dirs=ignore_dirs,
                verbose=verbose,
                ignore_path_contains_all=ignore_path_contains_all,
            )
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 2
        if not cc_violations and not cog_violations:
            # Always show that both metrics were checked
            print(
                f"Cyclomatic and cognitive complexity: all blocks within limit ({args.max}).",
                file=sys.stderr,
            )
            if verbose:
                print(
                    f"OK: no blocks exceed cyclomatic or cognitive complexity {args.max}",
                    file=sys.stderr,
                )
            return 0
        src = project_root / "src"
        if not src.is_dir():
            print(
                f"Error: project has no src/ directory: {project_root}",
                file=sys.stderr,
            )
            return 1
        has_failure = False
        if cc_violations:
            has_failure = True
        print(
            f"Radon (cyclomatic): {len(cc_violations)} block(s) exceed max {args.max}:",
            file=sys.stderr,
        )
        for file_path, name, lineno, complexity in sorted(
            cc_violations, key=lambda v: (v[0], v[2])
        ):
            print(
                f"  {file_path}:{lineno} {name} (cyclomatic={complexity})",
                file=sys.stderr,
            )
        if cog_violations:
            has_failure = True
        print(
            f"Cognitive complexity: {len(cog_violations)} function(s) exceed max {args.max}:",
            file=sys.stderr,
        )
        for file_path, name, lineno, complexity in sorted(
            cog_violations, key=lambda v: (v[0], v[2])
        ):
            print(
                f"  {file_path}:{lineno} {name} (cognitive={complexity})",
                file=sys.stderr,
            )
        return 1 if has_failure else 0

    if args.mode == "cc":
        run_cc(project_root, ignore_dirs, verbose, ignore_path_contains_all)
    elif args.mode == "raw":
        run_raw(project_root, ignore_dirs, verbose, ignore_path_contains_all)
    elif args.mode == "halstead":
        run_halstead(
            project_root, ignore_dirs, verbose, ignore_path_contains_all
        )
    elif args.mode == "mi":
        run_mi(
            project_root,
            ignore_dirs,
            verbose,
            count_multi=not args.no_multi,
            ignore_path_contains_all=ignore_path_contains_all,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
