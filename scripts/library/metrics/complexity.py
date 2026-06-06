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
import subprocess
import sys
import textwrap
from pathlib import Path

# Add library root to sys.path for shared imports
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.ollama_utils import (  # noqa: E402
    OLLAMA_DEFAULT_URL,
    OLLAMA_MAX_FIX_RETRIES,
    apply_and_verify_on_disk as _apply_and_verify_on_disk_shared,
    call_ollama as _call_ollama_raw,
    detect_indent as _detect_indent,
    extract_file_context as _extract_file_context,
    parse_ollama_response,
    run_ruff_check as _run_ruff_check_shared,
    run_pytest as _run_pytest_shared,
)

try:
    from radon.complexity import cc_visit
    from radon.metrics import h_visit, mi_visit
    from radon.raw import analyze as raw_analyze
    from radon.visitors import Class
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
DEFAULT_COMPLEXITY_OLLAMA_MODEL = "qwen3-coder:30b-ctx32k"
DEFAULT_COMPLEXITY_OLLAMA_NUM_PREDICT = 4096
DEFAULT_COMPLEXITY_OLLAMA_TIMEOUT_SECONDS = 180
DEFAULT_COMPLEXITY_OLLAMA_TEMPERATURE = 0.1
DEFAULT_COMPLEXITY_CONTEXT_CHARS = 8000
DEFAULT_COMPLEXITY_OLLAMA_KEEP_ALIVE = "10m"

# Blocks excluded from cognitive check (path_substring, function_name).
EXCLUDED_COGNITIVE_BLOCKS: list[tuple[str, str]] = [
    ("datrix_codegen_python/generators/event_generator.py", "_build_handlers_context"),
    ("datrix_codegen_python/generators/event_generator.py", "_build_event_schemas_context"),
    ("datrix_codegen_python/generators/model_generator.py", "_build_model_context"),
    ("datrix_codegen_python/generators/route_generator.py", "_add_imports_from_route_context"),
    ("datrix_codegen_common/transpiler/python_transpiler_core.py", "visit_call"),
    ("datrix_codegen_common/transpiler/python_transpiler_core.py", "visit_for_loop"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "_get_dto_fields"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "_map_type_to_validators"),
    (
        "datrix_codegen_typescript/generators/api/_controller_template_context.py",
        "build_controller_template_context",
    ),
    ("datrix_codegen_typescript/generators/entity_generator.py", "_map_relationship"),
    # datrix-common: model/semantic/types; datrix-language: parser/transformers
    ("datrix_common/datrix_model/base.py", "collect_refs"),
    ("datrix_language/parser/", "_merge_applications"),
    ("datrix_common/semantic/field_types.py", "visit_type"),
    ("datrix_common/semantic/imports.py", "_process_import_directive"),
    ("datrix_common/semantic/references.py", "_resolve_index_fields"),
    ("datrix_common/semantic/symbols.py", "_register_block_entities"),
    ("datrix_common/semantic/type_walker.py", "_apply_visitor"),
    ("datrix_common/semantic/type_checker.py", "visit_type"),
    ("datrix_common/semantic/type_walker.py", "_walk_service"),
    ("datrix_common/semantic/type_walker.py", "_walk_body"),
    ("datrix_language/transformers/transformer.py", "transform"),
    ("datrix_common/semantic/validators/cross_service.py", "_check_xsv001"),
    ("datrix_common/semantic/validators/entity.py", "_check_ent003"),
    ("datrix_common/semantic/validators/event.py", "_check_evt004"),
    ("datrix_common/semantic/validators/relationship.py", "_iter_relationships"),
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
    ("datrix_common/types/parser.py", "_parse_int_list"),
    ("datrix_common/types/parser.py", "_parse_type_expr_inner"),
]

# Blocks excluded from cyclomatic check (e.g. ABCs with many abstract method stubs).
# Each entry: (path_substring, block_name). Block is skipped if path contains substring and name matches.
EXCLUDED_CYCLOMATIC_BLOCKS: list[tuple[str, str]] = [
    ("datrix_common/generator.py", "Generator"),
    ("transpiler/base.py", "Transpiler"),
    ("datrix_codegen_common/transpiler/python_transpiler_core.py", "PythonTranspilerCore"),
    ("datrix_codegen_common/transpiler/typescript_transpiler_core.py", "TypeScriptTranspilerCore"),
    ("datrix_codegen_python/generators/api_test_generator.py", "ApiTestGenerator"),
    # TypeScript mirror: large orchestration class (same role as Python ApiTestGenerator).
    ("datrix_codegen_typescript/generators/api/api_test_generator.py", "ApiTestGenerator"),
    ("datrix_codegen_python/generators/cache_generator.py", "CacheGenerator"),
    ("datrix_codegen_python/generators/cqrs_generator.py", "CqrsGenerator"),
    ("datrix_codegen_python/generators/service/doc_generator.py", "DocGenerator"),
    ("datrix_codegen_python/generators/event_generator.py", "EventGenerator"),
    ("datrix_codegen_python/generators/entity_test_generator.py", "EntityTestGenerator"),
    ("datrix_codegen_python/generators/model_generator.py", "ModelGenerator"),
    ("datrix_codegen_python/generators/project_generator.py", "ProjectGenerator"),
    ("datrix_codegen_python/generators/route_generator.py", "RouteGenerator"),
    ("datrix_codegen_python/generators/schema_generator.py", "SchemaGenerator"),
    ("datrix_codegen_python/generators/integration_generator.py", "IntegrationGenerator"),
    ("datrix_codegen_python/generators/cross_cutting/integration_generator.py", "IntegrationGenerator"),
    ("datrix_codegen_python/generators/jobs_generator.py", "JobsGenerator"),
    ("datrix_codegen_python/generators/nosql_connection_generator.py", "NosqlConnectionGenerator"),
    ("datrix_codegen_python/generators/observability_generator.py", "ObservabilityGenerator"),
    ("datrix_codegen_python/generators/cross_cutting/observability_generator.py", "ObservabilityGenerator"),
    ("datrix_codegen_python/generators/pubsub_generator.py", "PubsubGenerator"),
    ("datrix_codegen_python/generators/rdbms_connection_generator.py", "RdbmsConnectionGenerator"),
    ("datrix_codegen_python/generators/resilience_generator.py", "ResilienceGenerator"),
    ("datrix_codegen_python/generators/cross_cutting/resilience_generator.py", "ResilienceGenerator"),
    ("datrix_codegen_python/generators/service_generator.py", "ServiceGenerator"),
    ("datrix_codegen_python/generators/test_factory_generator.py", "TestFactoryGenerator"),
    ("datrix_codegen_typescript/generators/controller_generator.py", "ControllerGenerator"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "DtoGenerator"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "_map_type_to_validators"),
    ("datrix_codegen_typescript/generators/entity_generator.py", "EntityGenerator"),
    ("datrix_codegen_typescript/generators/project_generator.py", "ProjectGenerator"),
    (
        "datrix_codegen_typescript/generators/api/_controller_template_context.py",
        "build_controller_template_context",
    ),
    ("datrix_codegen_typescript/plugin.py", "TypeScriptGenerator"),
    # datrix-common: model/semantic/types classes; datrix-language: parser/transformer classes
    ("datrix_common/datrix_model/api.py", "RestApi"),
    ("datrix_common/datrix_model/base.py", "Node"),
    ("datrix_common/datrix_model/base.py", "TypeContainer"),
    ("datrix_common/datrix_model/blocks.py", "RdbmsBlock"),
    ("datrix_common/datrix_model/blocks.py", "NosqlBlock"),
    ("datrix_common/datrix_model/callables.py", "Endpoint"),
    ("datrix_common/datrix_model/containers.py", "Application"),
    ("datrix_common/datrix_model/containers.py", "Service"),
    ("datrix_common/datrix_model/entity.py", "Entity"),
    ("datrix_language/parser/", "TreeSitterParser"),
    ("datrix_common/semantic/field_types.py", "_RefResolver"),
    ("datrix_common/semantic/type_checker.py", "_TypeValidator"),
    ("datrix_common/semantic/type_checker.py", "visit_type"),
    ("datrix_common/semantic/type_walker.py", "_walk_service"),
    ("datrix_common/semantic/type_walker.py", "_walk_body"),
    ("datrix_common/semantic/validators/api.py", "ApiValidator"),
    ("datrix_common/semantic/validators/cqrs.py", "CqrsValidator"),
    ("datrix_common/semantic/validators/cross_service.py", "CrossServiceValidator"),
    ("datrix_common/semantic/validators/entity.py", "EntityValidator"),
    ("datrix_common/semantic/validators/event.py", "EventValidator"),
    ("datrix_common/semantic/validators/relationship.py", "RelationshipValidator"),
    ("datrix_common/semantic/validators/service.py", "ServiceValidator"),
    ("datrix_common/semantic/validators/builtin_traits.py", "BuiltinTraitValidator"),
    ("datrix_common/semantic/validators/tenancy.py", "TenancyValidator"),
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
    ("datrix_common/types/parser.py", "_parse_int_list"),
    ("datrix_common/types/parser.py", "_parse_type_expr_inner"),
    ("datrix_common/types/registry.py", "TypeRegistry"),
    # Thin facade: many one-line delegations; class real_complexity is sum of trivial methods.
    ("datrix_common/plugin/registry.py", "PluginRegistry"),
]



def get_block_complexity(block: object) -> int | None:
    """Return cyclomatic complexity for a radon Function or Class block.

    For ``Class`` blocks, Radon's ``real_complexity`` sums every nested
    method's complexity. That rejects large cohesive types (for example
    code generators with many moderate methods) even when each method is
    within the limit. Use the class node's own ``complexity``; each method
    is still reported and checked as its own block.
    """
    if isinstance(block, Class):
        return getattr(block, "complexity", None)
    real = getattr(block, "real_complexity", None)
    if real is not None:
        return real
    return getattr(block, "complexity", None)


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




def _build_system_prompt(complexity_type: str) -> str:
    """Build a system prompt for the Ollama refactoring request."""
    if complexity_type == "cyclomatic":
        metric_explanation = (
            "Cyclomatic complexity counts linearly independent paths through code. "
            "Each `if`, `elif`, `for`, `while`, `except`, `and`, `or`, `assert`, "
            "and ternary expression adds 1. A function starts at 1."
        )
    else:
        metric_explanation = (
            "Cognitive complexity measures how hard code is to understand. "
            "Each `if`, `for`, `while`, `except` adds 1, plus a nesting penalty "
            "equal to the current nesting depth. Boolean sequences (`and`/`or`) "
            "add 1 per sequence. Nesting is the primary driver of high scores."
        )
    return (
        "You are a Python refactoring expert. You reduce function complexity "
        "while preserving exact behavior and all type annotations.\n\n"
        f"Metric: {complexity_type} complexity.\n"
        f"{metric_explanation}\n\n"
        "Strategies (use whichever apply):\n"
        "- Early returns / guard clauses to flatten nesting\n"
        "- Extract helper functions or methods (preserve `self` for instance methods)\n"
        "- Replace long if/elif chains with dispatch dicts or mappings\n"
        "- Replace nested conditionals with guard clauses\n"
        "- Use comprehensions instead of loop-accumulate patterns\n"
        "- Decompose compound boolean expressions into named predicates\n"
        "- Invert conditions to reduce nesting depth\n\n"
        "Output rules:\n"
        "- Return ONLY valid Python code inside a single ```python code fence\n"
        "- No explanations, no comments about the changes, no markdown outside the fence\n"
        "- Return only the replacement function block plus any extracted helpers; "
        "never include the surrounding class or module\n"
        "- Preserve the original indentation level\n"
        "- Every returned top-level `def` line must use the original base indentation; "
        "do not dedent below it\n"
        "- If extracting helpers, place them BEFORE the main function at the same "
        "indentation level\n"
        "- Every returned function, including extracted helpers, must individually "
        "satisfy the target complexity limit"
    )




def _measure_all_complexities(
    source: str,
    complexity_type: str,
    max_complexity: int,
) -> tuple[bool, list[tuple[str, int]]]:
    """Measure complexity of all functions in a source block.

    The source may be an indented fragment (e.g. a method extracted from a
    class body). We dedent before parsing so ``ast.parse`` succeeds regardless
    of leading indentation.

    Returns (all_pass, [(func_name, complexity), ...]).
    """
    dedented = textwrap.dedent(source)
    results: list[tuple[str, int]] = []
    if complexity_type == "cyclomatic":
        try:
            blocks = cc_visit(dedented)
        except Exception:
            return False, []
        for block in blocks:
            name = getattr(block, "name", "?")
            compl = get_block_complexity(block)
            if compl is not None:
                results.append((name, compl))
    else:
        if get_cognitive_complexity is None:
            return False, []
        try:
            tree = ast.parse(dedented)
        except SyntaxError:
            return False, []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            try:
                compl = get_cognitive_complexity(node)
            except Exception:
                continue
            results.append((node.name, compl))
    all_pass = all(c <= max_complexity for _, c in results)
    return all_pass, results


def _validate_fix_inmemory(
    new_content: str,
    fixed_source: str,
    complexity_type: str,
    max_complexity: int,
) -> tuple[bool, str | None, list[tuple[str, int]]]:
    """Validate a fix in-memory: syntax check then complexity re-check.

    Returns (passed, error_message_or_none, [(name, complexity), ...]).
    """
    try:
        ast.parse(new_content)
    except SyntaxError as e:
        return False, f"Syntax error: {e}", []
    all_pass, complexities = _measure_all_complexities(
        fixed_source, complexity_type, max_complexity,
    )
    if not all_pass:
        return False, None, complexities
    return True, None, complexities


def _normalize_replacement_block(source: str, target_indent: str) -> str:
    """Normalize a returned replacement block to the original function indentation."""
    dedented = textwrap.dedent(source).strip("\n")
    if not dedented:
        return ""
    dedented = _format_replacement_block_with_ruff(dedented)
    return textwrap.indent(dedented, target_indent, lambda line: bool(line.strip()))


def _format_replacement_block_with_ruff(dedented_source: str) -> str:
    """Best-effort Ruff formatting for a syntactically valid replacement fragment."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                "--stdin-filename",
                "complexity_fix_fragment.py",
                "-",
            ],
            input=dedented_source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return dedented_source
    if result.returncode != 0 or not result.stdout.strip():
        return dedented_source
    return result.stdout.strip("\n")


def _validate_replacement_shape(
    fixed_source: str,
    func_name: str,
) -> str | None:
    """Reject replacement shapes that cannot safely replace one function block."""
    try:
        tree = ast.parse(textwrap.dedent(fixed_source))
    except SyntaxError as e:
        return f"Syntax error in replacement block before insertion: {e}"

    top_level_defs = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    top_level_classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if top_level_classes:
        return (
            "Replacement includes a class wrapper. Return only helper functions/methods "
            "and the target function block, not the surrounding class."
        )
    if not any(node.name == func_name for node in top_level_defs):
        return f"Replacement does not include target function `{func_name}`."
    return None


def _build_retry_feedback(
    complexity_type: str,
    complexities: list[tuple[str, int]],
    max_complexity: int,
    validation_error: str | None = None,
    failed_source: str | None = None,
) -> str:
    """Build feedback for the LLM when a fix attempt failed."""
    parts: list[str] = []
    if validation_error:
        parts.append(f"Your previous attempt had a validation error: {validation_error}")
    for name, value in complexities:
        if value > max_complexity:
            parts.append(
                f"Function `{name}` still has {complexity_type} complexity "
                f"{value} (must be <= {max_complexity})."
            )
            parts.append(
                f"If `{name}` is an extracted helper, split that helper into smaller "
                "helpers too. Do not replace one complex function with one complex helper."
            )
    if validation_error and "unindent does not match" in validation_error:
        parts.append(
            "Fix indentation by returning one complete replacement block. Every top-level "
            "`def` in the replacement must start at the same base indentation as the "
            "original function; only nested function bodies should be indented further."
        )
    parts.append(
        "Try a different approach: extract more helpers, use early returns, "
        "replace conditionals with dispatch dicts, or flatten nesting further."
    )
    if failed_source:
        parts.append(
            "Previous replacement that failed validation. Use it only to understand "
            "what to fix; return a complete corrected replacement, not a patch:"
        )
        parts.append("```python")
        parts.append(_truncate_prompt_context(failed_source, 12000))
        parts.append("```")
    return "\n".join(parts)


def _build_disk_error_feedback(disk_error: str) -> str:
    """Build feedback for the LLM when ruff or tests fail after disk write."""
    if disk_error == "test_failure":
        return (
            "Your previous attempt caused test failures. "
            "Ensure the refactored code preserves exact behavior — "
            "do not change logic, only restructure for lower complexity."
        )
    # Ruff undefined-name errors (F821)
    return (
        f"Your previous attempt introduced undefined names:\n{disk_error}\n\n"
        "IMPORTANT: Only use names that are already imported or defined in the file. "
        "Do NOT invent new type names. If you extract a helper function, its parameter "
        "types must use only types visible in the file's import section shown in the context."
    )


def _truncate_prompt_context(file_context: str, max_context_chars: int) -> str:
    """Keep LLM context bounded; function source is always sent separately."""
    if max_context_chars <= 0 or not file_context:
        return ""
    if len(file_context) <= max_context_chars:
        return file_context
    return (
        file_context[:max_context_chars].rstrip()
        + "\n\n# Context truncated to fit the local LLM prompt budget."
    )


def _effective_num_predict(function_source: str, configured_num_predict: int) -> int:
    """Increase output budget only for large functions likely to need helpers."""
    line_count = len(function_source.splitlines())
    if line_count >= 180:
        return max(configured_num_predict, 12288)
    if line_count >= 100:
        return max(configured_num_predict, 8192)
    return configured_num_predict


def call_ollama(
    function_source: str,
    func_name: str,
    complexity_type: str,
    complexity_value: int,
    max_complexity: int,
    ollama_url: str,
    model: str,
    timeout_seconds: int,
    num_predict: int,
    temperature: float,
    keep_alive: str,
    file_context: str = "",
    retry_feedback: str | None = None,
) -> str:
    """Send function to Ollama for complexity reduction. Return fixed source."""
    indent_count = len(_detect_indent(function_source))
    system_prompt = _build_system_prompt(complexity_type)

    parts: list[str] = [
        f"Refactor the function `{func_name}` to reduce its {complexity_type} "
        f"complexity from {complexity_value} to at most {max_complexity}.\n",
    ]
    if retry_feedback:
        parts.append(f"IMPORTANT — Previous attempt feedback:\n{retry_feedback}\n")
    parts.append(
        "Requirements:\n"
        f"- Maintain the same function signature, behavior, and base indentation "
        f"({indent_count} spaces)\n"
        "- You may extract helper functions/methods at the same indent level, "
        "placed BEFORE the main function\n"
        "- If the function is a class method (has `self` parameter), extracted "
        "helpers should also be methods with a `self` parameter\n"
        f"- Every returned function/helper must have {complexity_type} complexity "
        f"<= {max_complexity}; do not leave complexity concentrated in one helper\n"
        "- All returned top-level def lines must use the same base indentation as "
        "the original function; do not dedent below that base indentation\n"
        "- Return only the replacement function block plus any extracted helpers; "
        "do not include the surrounding class or unrelated methods\n"
        "- Preserve all type annotations\n"
        "- Return ONLY Python code inside a single ```python code fence"
    )
    if file_context:
        parts.append(f"\n{file_context}")
    parts.append(f"\nFunction to refactor:\n```python\n{function_source}```")
    user_prompt = "\n".join(parts)

    response = _call_ollama_raw(
        system_prompt, user_prompt, ollama_url, model,
        timeout=timeout_seconds,
        num_predict=_effective_num_predict(function_source, num_predict),
        temperature=temperature,
        keep_alive=keep_alive,
    )
    if response is None:
        raise RuntimeError(
            f"Failed to get response from Ollama at {ollama_url}"
        )

    result = parse_ollama_response(response)
    if result is None:
        raise RuntimeError("Could not parse code from Ollama response")
    return result




def _attempt_single_ollama_fix(
    func_source: str,
    func_name: str,
    comp_type: str,
    complexity: int,
    max_complexity: int,
    ollama_url: str,
    model: str,
    timeout_seconds: int,
    num_predict: int,
    temperature: float,
    keep_alive: str,
    file_context: str,
    original_indent: str,
    lines: list[str],
    start: int,
    end: int,
    retry_feedback: str | None,
) -> tuple[str | None, str | None, list[tuple[str, int]], str]:
    """Run one Ollama attempt and validate in-memory.

    Returns (new_content_or_none, error_message_or_none, complexities, fixed_source).
    On Ollama connection errors, raises RuntimeError.
    """
    fixed_source = call_ollama(
        func_source, func_name, comp_type, complexity,
        max_complexity, ollama_url, model,
        timeout_seconds, num_predict, temperature, keep_alive,
        file_context=file_context,
        retry_feedback=retry_feedback,
    )
    fixed_source = _normalize_replacement_block(fixed_source, original_indent)
    if not fixed_source.endswith("\n"):
        fixed_source += "\n"

    shape_error = _validate_replacement_shape(fixed_source, func_name)
    if shape_error:
        return None, shape_error, [], fixed_source

    new_lines = lines[: start - 1] + [fixed_source] + lines[end:]
    new_content = "".join(new_lines)

    passed, error_msg, complexities = _validate_fix_inmemory(
        new_content, fixed_source, comp_type, max_complexity,
    )
    if not passed:
        return None, error_msg, complexities, fixed_source
    return new_content, None, complexities, fixed_source


def _attempt_fix_violation(
    file_path: Path,
    source: str,
    func_name: str,
    lineno: int,
    complexity: int,
    comp_type: str,
    max_complexity: int,
    ollama_url: str,
    model: str,
    timeout_seconds: int,
    num_predict: int,
    temperature: float,
    keep_alive: str,
    max_context_chars: int,
    verbose: bool,
    unit_tests: bool,
    project_root: Path,
    max_retries: int,
) -> bool:
    """Attempt to fix a single violation with retries. Return True if fixed."""
    node = find_function_node(source, func_name, lineno)
    if node is None:
        if verbose:
            print(
                f"Skipping {func_name} at {file_path}:{lineno} (not a function)",
                file=sys.stderr,
            )
        return False

    original_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    lines = source.splitlines(keepends=True)
    start, end = get_function_line_range(node)
    func_source = "".join(lines[start - 1 : end])
    original_indent = _detect_indent(func_source)
    file_context = _truncate_prompt_context(
        _extract_file_context(source, func_name, lineno),
        max_context_chars,
    )

    print(
        f"\nFixing: {file_path}:{lineno} {func_name} "
        f"({comp_type}={complexity}, max={max_complexity})",
        file=sys.stderr,
    )
    print(
        f"Extracted function ({end - start + 1} lines, lines {start}-{end})",
        file=sys.stderr,
    )

    retry_feedback: str | None = None
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"  Retry {attempt}/{max_retries}...", file=sys.stderr)
        print(f"  Sending to Ollama ({model})...", file=sys.stderr)

        try:
            new_content, error_msg, complexities, failed_source = _attempt_single_ollama_fix(
                func_source, func_name, comp_type, complexity, max_complexity,
                ollama_url, model, timeout_seconds, num_predict, temperature,
                keep_alive, file_context, original_indent,
                lines, start, end, retry_feedback,
            )
        except RuntimeError as e:
            print(f"  Ollama error: {e}", file=sys.stderr)
            return False

        if new_content is None:
            _log_validation_failure(error_msg, complexities, comp_type, max_complexity)
            if attempt < max_retries:
                retry_feedback = _build_retry_feedback(
                    comp_type, complexities, max_complexity, error_msg,
                    failed_source=failed_source,
                )
                continue
            print(f"  All {max_retries} attempt(s) failed.", file=sys.stderr)
            return False

        # In-memory checks passed — verify file not modified, then disk checks
        disk_ok, disk_error = _apply_and_verify_on_disk(
            file_path, source, new_content, original_hash,
            verbose, unit_tests, project_root,
        )
        if not disk_ok:
            if disk_error == "file_modified":
                return False
            if attempt < max_retries:
                retry_feedback = _build_disk_error_feedback(disk_error)
                continue
            print(f"  All {max_retries} attempt(s) failed.", file=sys.stderr)
            return False

        print(f"Fixed: {file_path}:{start} {func_name}", file=sys.stderr)
        return True
    return False


def _log_validation_failure(
    error_msg: str | None,
    complexities: list[tuple[str, int]],
    comp_type: str,
    max_complexity: int,
) -> None:
    """Log why an in-memory validation failed."""
    if error_msg:
        print(f"  Validation failed: {error_msg}", file=sys.stderr)
    else:
        for name, val in complexities:
            if val > max_complexity:
                print(
                    f"  {name}: {comp_type}={val} (still > {max_complexity})",
                    file=sys.stderr,
                )


def _apply_and_verify_on_disk(
    file_path: Path,
    original_source: str,
    new_content: str,
    original_hash: str,
    verbose: bool,
    unit_tests: bool,
    project_root: Path,
) -> tuple[bool, str]:
    """Write fixed file, run ruff/pytest. Revert on failure.

    Returns (success, error_details). error_details is non-empty when ruff
    or tests fail, suitable for inclusion in retry feedback.
    """
    if verbose:
        print(f"  Verifying fix on disk for {file_path}...", file=sys.stderr)

    success, error_details = _apply_and_verify_on_disk_shared(
        file_path, original_source, new_content, original_hash,
        project_root, run_tests=unit_tests,
    )

    if not success:
        if error_details == "file_modified":
            print(
                f"  File {file_path} was modified during processing, skipping.",
                file=sys.stderr,
            )
        elif error_details == "test_failure":
            print("  Reverting due to test failures.", file=sys.stderr)
        elif error_details:
            print("  Reverting due to ruff errors.", file=sys.stderr)
            if verbose:
                for line in error_details.splitlines():
                    print(f"    {line}", file=sys.stderr)

    return success, error_details


def _collect_violations(
    project_root: Path,
    max_complexity: int,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None,
) -> list[tuple[str, str, int, int, str]]:
    """Collect, combine, deduplicate, and sort all complexity violations."""
    cc_violations = run_check(
        project_root, max_complexity, ignore_dirs, verbose, ignore_path_contains_all,
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

    all_violations: list[tuple[str, str, int, int, str]] = []
    for path, name, lineno, compl in cc_violations:
        all_violations.append((path, name, lineno, compl, "cyclomatic"))
    for path, name, lineno, compl in cog_violations:
        all_violations.append((path, name, lineno, compl, "cognitive"))

    all_violations.sort(key=lambda v: v[3], reverse=True)

    seen: set[tuple[str, str, int]] = set()
    unique: list[tuple[str, str, int, int, str]] = []
    for v in all_violations:
        key = (v[0], v[1], v[2])
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def run_fix(
    project_root: Path,
    max_complexity: int,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None,
    ollama_url: str,
    model: str,
    timeout_seconds: int,
    num_predict: int,
    temperature: float,
    keep_alive: str,
    max_context_chars: int,
    unit_tests: bool = False,
    max_retries: int = OLLAMA_MAX_FIX_RETRIES,
    fix_all: bool = False,
) -> int:
    """Fix complexity violations using Ollama. Return exit code.

    Tries violations from worst to least complex, with up to max_retries
    Ollama attempts per violation. On any failure (Ollama error, syntax error,
    complexity still too high, ruff check, or test failure), reverts the file
    and moves to the next violation.

    With fix_all=False (default), exits after the first successful fix.
    With fix_all=True, continues fixing all violations. After a file is
    modified, subsequent violations in that file are re-collected to account
    for shifted line numbers.
    """
    unique = _collect_violations(
        project_root, max_complexity, ignore_dirs, verbose, ignore_path_contains_all,
    )
    if not unique:
        print("No complexity violations found. Nothing to fix.", file=sys.stderr)
        return 0

    fixed_count = 0
    failed_count = 0
    modified_files: set[str] = set()

    for file_path_str, func_name, lineno, complexity, comp_type in unique:
        if file_path_str in modified_files:
            # Line numbers have shifted; skip — will be re-collected in next pass
            continue
        file_path = Path(file_path_str)
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue

        if _attempt_fix_violation(
            file_path, source, func_name, lineno, complexity, comp_type,
            max_complexity, ollama_url, model,
            timeout_seconds, num_predict, temperature, keep_alive,
            max_context_chars,
            verbose, unit_tests,
            project_root, max_retries,
        ):
            fixed_count += 1
            modified_files.add(file_path_str)
            if not fix_all:
                print("Re-run the script to fix more violations.", file=sys.stderr)
                return 0
        else:
            failed_count += 1

    if fix_all and modified_files:
        # Re-collect to handle violations in modified files (shifted line numbers)
        remaining = _collect_violations(
            project_root, max_complexity, ignore_dirs, verbose,
            ignore_path_contains_all,
        )
        for file_path_str, func_name, lineno, complexity, comp_type in remaining:
            file_path = Path(file_path_str)
            try:
                source = file_path.read_text(encoding="utf-8")
            except OSError as e:
                print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
                continue
            if _attempt_fix_violation(
                file_path, source, func_name, lineno, complexity, comp_type,
                max_complexity, ollama_url, model,
                timeout_seconds, num_predict, temperature, keep_alive,
                max_context_chars,
                verbose, unit_tests,
                project_root, max_retries,
            ):
                fixed_count += 1
            else:
                failed_count += 1

    if fix_all:
        print(
            f"\nFix-all complete: {fixed_count} fixed, {failed_count} failed.",
            file=sys.stderr,
        )
        return 0 if fixed_count > 0 or failed_count == 0 else 1

    print("No violations could be fixed.", file=sys.stderr)
    return 1


def run_cc(
    project_root: Path,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None = None,
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
    "--fix-all",
    action="store_true",
    help="Fix ALL violations (not just the first). Implies --fix.",
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
    default=DEFAULT_COMPLEXITY_OLLAMA_MODEL,
    help=f"Ollama model name (default: {DEFAULT_COMPLEXITY_OLLAMA_MODEL}).",
    )
    parser.add_argument(
    "--ollama-timeout",
    type=int,
    default=DEFAULT_COMPLEXITY_OLLAMA_TIMEOUT_SECONDS,
    metavar="SECONDS",
    help=(
        "Ollama request timeout in seconds "
        f"(default: {DEFAULT_COMPLEXITY_OLLAMA_TIMEOUT_SECONDS})."
    ),
    )
    parser.add_argument(
    "--ollama-num-predict",
    type=int,
    default=DEFAULT_COMPLEXITY_OLLAMA_NUM_PREDICT,
    metavar="N",
    help=(
        "Ollama max generated tokens per refactor attempt "
        f"(default: {DEFAULT_COMPLEXITY_OLLAMA_NUM_PREDICT})."
    ),
    )
    parser.add_argument(
    "--ollama-temperature",
    type=float,
    default=DEFAULT_COMPLEXITY_OLLAMA_TEMPERATURE,
    metavar="FLOAT",
    help=(
        "Ollama sampling temperature "
        f"(default: {DEFAULT_COMPLEXITY_OLLAMA_TEMPERATURE})."
    ),
    )
    parser.add_argument(
    "--ollama-keep-alive",
    type=str,
    default=DEFAULT_COMPLEXITY_OLLAMA_KEEP_ALIVE,
    metavar="DURATION",
    help=(
        "How long Ollama should keep the model loaded between attempts "
        f"(default: {DEFAULT_COMPLEXITY_OLLAMA_KEEP_ALIVE})."
    ),
    )
    parser.add_argument(
    "--max-context-chars",
    type=int,
    default=DEFAULT_COMPLEXITY_CONTEXT_CHARS,
    metavar="N",
    help=(
        "Maximum file-context characters to include in each LLM prompt; "
        "the target function is always included in full "
        f"(default: {DEFAULT_COMPLEXITY_CONTEXT_CHARS})."
    ),
    )
    parser.add_argument(
    "--test",
    action="store_true",
    help="Run pytest after fix to verify; revert if tests fail (--fix only).",
    )
    parser.add_argument(
    "--max-retries",
    type=int,
    default=OLLAMA_MAX_FIX_RETRIES,
    metavar="N",
    help=f"Max Ollama retry attempts per violation (default: {OLLAMA_MAX_FIX_RETRIES}).",
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

    if args.fix or args.fix_all:
        if args.mode != "check":
            print(
                "Error: --fix/--fix-all can only be used with --mode check.",
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
            timeout_seconds=args.ollama_timeout,
            num_predict=args.ollama_num_predict,
            temperature=args.ollama_temperature,
            keep_alive=args.ollama_keep_alive,
            max_context_chars=args.max_context_chars,
            unit_tests=args.test,
            max_retries=args.max_retries,
            fix_all=args.fix_all,
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
