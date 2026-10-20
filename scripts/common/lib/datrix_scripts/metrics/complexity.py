"""
Run Radon metrics on each selected Datrix project's src tree, or check named files.

``scripts/metrics/complexity.ps1`` (and its ``.sh`` twin) runs this module; ``dev/code_scan.py`` and the
scripts contract checks import its checks. Modes:
    check - Enforce max cyclomatic and cognitive complexity; a project fails if any block exceeds --max.
    cc - Report cyclomatic complexity (McCabe) per block.
    raw - Report raw metrics (SLOC, comment/blank lines, LOC, LLOC) per file.
    halstead - Report Halstead metrics (volume, difficulty, etc.) per file.
    mi - Report Maintainability Index per file.

Only analyzes Python files under each project's src/; tests are excluded. In mode=check, both cyclomatic
complexity (Radon) and cognitive complexity (via cognitive_complexity) are enforced. ``--files`` checks
exactly the named .py files instead (mode=check only). ``--fix`` / ``--fix-all`` ask a local model to
rewrite the worst violation(s), each validated and reverted on failure.

Exit codes: 0 = every project passed (or every fix run completed); 1 = a violation, a failed project, a
refused combination of options or selection; 2 = a usage error.

Usage (PYTHONPATH=scripts/common/lib; the wrapper sets it):
    python -m datrix_scripts.metrics.complexity datrix-common
    python -m datrix_scripts.metrics.complexity datrix-common --mode=raw
    python -m datrix_scripts.metrics.complexity --files=a.py,b.py
    python -m datrix_scripts.metrics.complexity --self-test
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.llm_code_fix import (
    MAX_FIX_RETRIES,
    parse_code_response,
)
from datrix_scripts.llm_code_fix import (
    apply_and_verify_on_disk as _apply_and_verify_on_disk_shared,
)
from datrix_scripts.llm_code_fix import (
    detect_indent as _detect_indent,
)
from datrix_scripts.llm_code_fix import (
    extract_file_context as _extract_file_context,
)
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.local_llm import (
    ChatRequest,
    LocalLlmPool,
    LocalLlmSettings,
    LocalLlmUnavailable,
    add_wrapper_llm_arguments,
    wrapper_llm_settings,
)
from datrix_scripts.metrics.projects import (
    CODE_SHAPE_WORDING,
    COMPLETED_COUNT_LABEL,
    DONE_LABEL,
    EXIT_FAILED,
    EXIT_PASSED,
    STOP_MESSAGE_FLAG,
    ProjectSelectionError,
    add_project_arguments,
    line_buffered_stdout,
    plant_workspace,
    print_summary,
    run_projects,
    select_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import PACKAGE_DEV_EXTRAS, SCRIPTS_DEPENDENCY_GROUP, missing_declared_tool

try:
    from radon.complexity import cc_visit
    from radon.metrics import h_visit, mi_visit
    from radon.raw import analyze as raw_analyze
    from radon.visitors import Class
except ImportError as exc:
    raise SystemExit(missing_declared_tool("radon", PACKAGE_DEV_EXTRAS)) from exc

try:
    from cognitive_complexity.api import get_cognitive_complexity
except ImportError as exc:
    raise SystemExit(missing_declared_tool("cognitive_complexity", SCRIPTS_DEPENDENCY_GROUP)) from exc

DEFAULT_MAX_COMPLEXITY = 15
DEFAULT_IGNORE_DIRS = ("tests", "test", "__pycache__", ".git")
DEFAULT_COMPLEXITY_LLM_NUM_PREDICT = 4096
DEFAULT_COMPLEXITY_LLM_TEMPERATURE = 0.1
DEFAULT_COMPLEXITY_CONTEXT_CHARS = 8000

# Blocks excluded from cognitive check (path_substring, function_name).
EXCLUDED_COGNITIVE_BLOCKS: list[tuple[str, str]] = [
    ("datrix_codegen_python/generators/event_generator.py", "_build_handlers_context"),
    ("datrix_codegen_python/generators/event_generator.py", "_build_event_schemas_context"),
    ("datrix_codegen_python/generators/model_generator.py", "_build_model_context"),
    ("datrix_codegen_python/generators/route_generator.py", "_add_imports_from_route_context"),
    ("datrix_codegen_python/transpiler/core.py", "visit_call"),
    ("datrix_codegen_python/transpiler/core.py", "visit_for_loop"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "_get_dto_fields"),
    ("datrix_codegen_typescript/generators/dto_generator.py", "_map_type_to_validators"),
    (
        "datrix_codegen_typescript/generators/api/_controller_template_context.py",
        "build_controller_template_context",
    ),
    ("datrix_codegen_typescript/generators/entity_generator.py", "_map_relationship"),
    # datrix-common: model/types; datrix-semantic; datrix-language: parser/transformers
    ("datrix_common/datrix_model/base.py", "collect_refs"),
    ("datrix_language/parser/", "_merge_applications"),
    ("datrix_semantic/field_types.py", "visit_type"),
    ("datrix_semantic/imports.py", "_process_import_directive"),
    ("datrix_semantic/references.py", "_resolve_index_fields"),
    ("datrix_semantic/symbols.py", "_register_block_entities"),
    ("datrix_semantic/type_walker.py", "_apply_visitor"),
    ("datrix_semantic/type_checker.py", "visit_type"),
    ("datrix_semantic/type_walker.py", "_walk_service"),
    ("datrix_semantic/type_walker.py", "_walk_body"),
    ("datrix_language/transformers/transformer.py", "transform"),
    ("datrix_semantic/validators/cross_service_entity_ambiguity.py", "_check_xsv001"),
    ("datrix_semantic/validators/entity.py", "_check_ent003"),
    ("datrix_semantic/validators/event.py", "_check_evt004"),
    ("datrix_semantic/validators/relationship.py", "_iter_relationships"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_call_expression"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_string_literal"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_lambda_expression"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_fstring"),
    ("datrix_language/transformers/statement_transformer.py", "_transform_try_statement"),
    # datrix-language's transformers/ is one module per top-level element kind
    # the three transforms below moved out of transformer.py with
    # their bodies unchanged. The rest of the old transformer.py god-method entries
    # named functions that no longer exist anywhere and matched nothing.
    ("datrix_language/transformers/directives.py", "transform_import_statement"),
    ("datrix_language/transformers/system.py", "transform_system_block"),
    ("datrix_language/transformers/service.py", "transform_service_block"),
    ("datrix_common/types/parser.py", "_parse_int_list"),
    ("datrix_common/types/parser.py", "_parse_type_expr_inner"),
]

# Blocks excluded from cyclomatic check (e.g. ABCs with many abstract method stubs).
# Each entry: (path_substring, block_name). Block is skipped if path contains substring and name matches.
EXCLUDED_CYCLOMATIC_BLOCKS: list[tuple[str, str]] = [
    ("datrix_common/generator.py", "Generator"),
    ("transpiler/base.py", "Transpiler"),
    ("datrix_codegen_python/transpiler/core.py", "PythonTranspilerCore"),
    ("datrix_codegen_typescript_core/transpiler/core.py", "TypeScriptTranspilerCore"),
    ("datrix_codegen_python/generators/api_test_generator.py", "ApiTestGenerator"),
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
    ("datrix_codegen_python/generators/observability_generator.py", "ObservabilityGenerator"),
    ("datrix_codegen_python/generators/cross_cutting/observability_generator.py", "ObservabilityGenerator"),
    ("datrix_codegen_python/generators/pubsub_generator.py", "PubsubGenerator"),
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
    # datrix-common: model/types classes; datrix-semantic; datrix-language: parser/transformer classes
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
    ("datrix_semantic/field_types.py", "_RefResolver"),
    ("datrix_semantic/type_checker.py", "_TypeValidator"),
    ("datrix_semantic/type_checker.py", "visit_type"),
    ("datrix_semantic/type_walker.py", "_walk_service"),
    ("datrix_semantic/type_walker.py", "_walk_body"),
    ("datrix_semantic/validators/api.py", "ApiValidator"),
    ("datrix_semantic/validators/cqrs.py", "CqrsValidator"),
    (
        "datrix_semantic/validators/cross_service_call_sites.py",
        "CrossServiceCallSitesValidator",
    ),
    ("datrix_semantic/validators/entity.py", "EntityValidator"),
    ("datrix_semantic/validators/event.py", "EventValidator"),
    ("datrix_semantic/validators/relationship.py", "RelationshipValidator"),
    ("datrix_semantic/validators/service.py", "ServiceValidator"),
    ("datrix_semantic/validators/builtin_traits.py", "BuiltinTraitValidator"),
    ("datrix_semantic/validators/tenancy.py", "TenancyValidator"),
    # Thin facades: many one-line delegations into the member-kind modules beside
    # them; each class's real_complexity is the sum of trivial methods.
    ("datrix_language/transformers/api/facade.py", "ApiTransformer"),
    ("datrix_language/transformers/entity/facade.py", "EntityTransformer"),
    ("datrix_language/transformers/cqrs_transformer.py", "CqrsTransformer"),
    ("datrix_language/transformers/expression_transformer.py", "ExpressionTransformer"),
    ("datrix_language/transformers/expression_transformer.py", "_transform_lambda_expression"),
    ("datrix_language/transformers/statement_transformer.py", "StatementTransformer"),
    ("datrix_language/transformers/transformer.py", "ASTTransformer"),
    ("datrix_language/transformers/transformer.py", "transform"),
    ("datrix_language/transformers/system.py", "transform_system_block"),
    ("datrix_language/transformers/service.py", "transform_service_block"),
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


def files_to_check(
    project_root: Path | None,
    ignore_dirs: tuple[str, ...],
    ignore_path_contains_all: tuple[str, ...] | None,
    files: Sequence[Path] | None,
) -> list[Path]:
    """The explicit *files* when given, else every Python file under ``project_root/src``."""
    if files is not None:
        return sorted(files)
    if project_root is None:
        raise ValueError("Pass either a project root or an explicit file list to check.")
    return collect_py_files(project_root, ignore_dirs, ignore_path_contains_all)


def run_check(
    project_root: Path | None,
    max_complexity: int,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None = None,
    files: Sequence[Path] | None = None,
) -> list[tuple[str, str, int, int]]:
    """Check that no block exceeds max complexity. Return list of violations."""
    violations: list[tuple[str, str, int, int]] = []
    for file_path in files_to_check(project_root, ignore_dirs, ignore_path_contains_all, files):
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
    project_root: Path | None,
    max_complexity: int,
    ignore_dirs: tuple[str, ...],
    verbose: bool,
    ignore_path_contains_all: tuple[str, ...] | None = None,
    files: Sequence[Path] | None = None,
) -> list[tuple[str, str, int, int]]:
    """Check that no function or async function exceeds max cognitive complexity. Return list of violations."""
    violations: list[tuple[str, str, int, int]] = []
    for file_path in files_to_check(project_root, ignore_dirs, ignore_path_contains_all, files):
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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
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
    """Build a system prompt for the local-model refactoring request."""
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


def request_refactor(
    function_source: str,
    func_name: str,
    complexity_type: str,
    complexity_value: int,
    max_complexity: int,
    pool: LocalLlmPool,
    num_predict: int,
    temperature: float,
    file_context: str = "",
    retry_feedback: str | None = None,
) -> str | None:
    """Ask a local model to reduce the function's complexity.

    Returns the replacement code, or None when the answer holds no code block (a failed
    attempt, retried with feedback). Raises LocalLlmUnavailable when no server can answer.
    """
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

    reply = pool.chat(ChatRequest(
        system=system_prompt,
        user=user_prompt,
        temperature=temperature,
        max_tokens=_effective_num_predict(function_source, num_predict),
    ))
    return parse_code_response(reply.text)


def _attempt_single_llm_fix(
    func_source: str,
    func_name: str,
    comp_type: str,
    complexity: int,
    max_complexity: int,
    pool: LocalLlmPool,
    num_predict: int,
    temperature: float,
    file_context: str,
    original_indent: str,
    lines: list[str],
    start: int,
    end: int,
    retry_feedback: str | None,
) -> tuple[str | None, str | None, list[tuple[str, int]], str]:
    """Run one model attempt and validate in-memory.

    Returns (new_content_or_none, error_message_or_none, complexities, fixed_source).
    Raises LocalLlmUnavailable when no server can answer.
    """
    fixed_source = request_refactor(
        func_source, func_name, comp_type, complexity,
        max_complexity, pool, num_predict, temperature,
        file_context=file_context,
        retry_feedback=retry_feedback,
    )
    if fixed_source is None:
        return None, "The answer held no Python code block.", [], ""
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
    pool: LocalLlmPool,
    num_predict: int,
    temperature: float,
    max_context_chars: int,
    verbose: bool,
    unit_tests: bool,
    project_root: Path,
    max_retries: int,
) -> bool:
    """Attempt to fix a single violation with retries. Return True if fixed.

    Raises LocalLlmUnavailable when no server can answer: every later violation would
    fail the same way, so the run stops rather than reporting each one as unfixable.
    """
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
        print(f"  Sending to {pool.activate().label()}...", file=sys.stderr)

        new_content, error_msg, complexities, failed_source = _attempt_single_llm_fix(
            func_source, func_name, comp_type, complexity, max_complexity,
            pool, num_predict, temperature, file_context, original_indent,
            lines, start, end, retry_feedback,
        )

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
    cog_violations = run_check_cognitive(
        project_root, max_complexity, ignore_dirs, verbose, ignore_path_contains_all,
    )

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
    pool: LocalLlmPool,
    num_predict: int,
    temperature: float,
    max_context_chars: int,
    unit_tests: bool = False,
    max_retries: int = MAX_FIX_RETRIES,
    fix_all: bool = False,
) -> int:
    """Fix complexity violations using a local model. Return exit code.

    Tries violations from worst to least complex, with up to max_retries
    model attempts per violation. On any failure (no code in the answer, syntax
    error, complexity still too high, ruff check, or test failure), reverts the
    file and moves to the next violation. Raises LocalLlmUnavailable when no
    server can answer.

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
            max_complexity, pool, num_predict, temperature,
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
                max_complexity, pool, num_predict, temperature,
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


def check_files(files: Sequence[Path], max_complexity: int) -> int:
    """Check exactly *files* for cyclomatic and cognitive complexity above *max_complexity*.

    Returns 0 when every block is within the limit, 1 on a violation or a missing or non-.py file.
    """
    bad = [str(path) for path in files if not path.is_file() or path.suffix != ".py"]
    if bad:
        print(f"Error: not an existing .py file: {bad}", file=sys.stderr)
        return 1
    resolved = [path.resolve() for path in files]
    cc_violations = run_check(None, max_complexity, (), False, files=resolved)
    cog_violations = run_check_cognitive(None, max_complexity, (), False, files=resolved)
    for label, violations in (("cyclomatic", cc_violations), ("cognitive", cog_violations)):
        for file_path, name, lineno, complexity in sorted(violations, key=lambda v: (v[0], v[2])):
            print(f"  {file_path}:{lineno} {name} ({label}={complexity})", file=sys.stderr)
    total = len(cc_violations) + len(cog_violations)
    print(
        f"{len(resolved)} file(s): {len(cc_violations)} cyclomatic and {len(cog_violations)} cognitive "
        f"violation(s) above {max_complexity}.",
        file=sys.stderr,
    )
    return 1 if total else 0


@dataclass(frozen=True)
class FixOptions:
    """The wrapper's ``-Fix`` / ``-FixAll`` settings: how a local model is asked to rewrite a violation."""

    fix_all: bool
    unit_tests: bool
    max_retries: int
    num_predict: int
    temperature: float
    max_context_chars: int
    llm_settings: LocalLlmSettings


@dataclass(frozen=True)
class AnalysisOptions:
    """What every project's analysis of one run shares; *fix* is set for a ``-Fix`` / ``-FixAll`` run."""

    mode: str
    max_complexity: int
    verbose: bool
    fix: FixOptions | None


def _print_violations(heading: str, label: str, violations: list[tuple[str, str, int, int]]) -> None:
    print(heading, file=sys.stderr)
    for file_path, name, lineno, complexity in sorted(violations, key=lambda v: (v[0], v[2])):
        print(f"  {file_path}:{lineno} {name} ({label}={complexity})", file=sys.stderr)


def _check_project(project_root: Path, max_complexity: int, verbose: bool, ignored: tuple[str, ...]) -> int:
    """Mode check over *project_root*: 0 when no block exceeds *max_complexity*, else 1 with each violation."""
    cc_violations = run_check(project_root, max_complexity, DEFAULT_IGNORE_DIRS, verbose, ignored)
    cog_violations = run_check_cognitive(project_root, max_complexity, DEFAULT_IGNORE_DIRS, verbose, ignored)
    if not cc_violations and not cog_violations:
        print(f"Cyclomatic and cognitive complexity: all blocks within limit ({max_complexity}).", file=sys.stderr)
        if verbose:
            print(f"OK: no blocks exceed cyclomatic or cognitive complexity {max_complexity}", file=sys.stderr)
        return EXIT_PASSED
    _print_violations(
        f"Radon (cyclomatic): {len(cc_violations)} block(s) exceed max {max_complexity}:", "cyclomatic", cc_violations
    )
    _print_violations(
        f"Cognitive complexity: {len(cog_violations)} function(s) exceed max {max_complexity}:",
        "cognitive",
        cog_violations,
    )
    return EXIT_FAILED


def _fix_project(project_root: Path, options: AnalysisOptions, fix: FixOptions, ignored: tuple[str, ...]) -> int:
    try:
        return run_fix(
            project_root,
            max_complexity=options.max_complexity,
            ignore_dirs=DEFAULT_IGNORE_DIRS,
            verbose=options.verbose,
            ignore_path_contains_all=ignored,
            pool=LocalLlmPool(fix.llm_settings),
            num_predict=fix.num_predict,
            temperature=fix.temperature,
            max_context_chars=fix.max_context_chars,
            unit_tests=fix.unit_tests,
            max_retries=fix.max_retries,
            fix_all=fix.fix_all,
        )
    except LocalLlmUnavailable as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_LLM_UNAVAILABLE


def _report(project_root: Path, mode: str, verbose: bool, ignored: tuple[str, ...]) -> None:
    """The report of a mode other than check."""
    if mode == MODE_CC:
        run_cc(project_root, DEFAULT_IGNORE_DIRS, verbose, ignored)
    elif mode == MODE_RAW:
        run_raw(project_root, DEFAULT_IGNORE_DIRS, verbose, ignored)
    elif mode == MODE_HALSTEAD:
        run_halstead(project_root, DEFAULT_IGNORE_DIRS, verbose, ignored)
    elif mode == MODE_MI:
        run_mi(project_root, DEFAULT_IGNORE_DIRS, verbose, count_multi=True, ignore_path_contains_all=ignored)
    else:
        raise ValueError(f"Unknown complexity mode {mode!r}; expected one of {', '.join(MODES)}.")


def analyze_project(project_root: Path, options: AnalysisOptions, ignored: tuple[str, ...]) -> int:
    """One project's run in *options.mode* (a fix run when *options.fix* is set); its exit code.

    *ignored* names the path segments a file's path must all hold to be skipped (empty: none).
    """
    project_root = project_root.resolve()
    if not project_root.is_dir():
        print(f"Error: project root is not a directory: {project_root}", file=sys.stderr)
        return EXIT_FAILED
    if options.fix is not None:
        return _fix_project(project_root, options, options.fix, ignored)
    if options.mode == MODE_CHECK:
        return _check_project(project_root, options.max_complexity, options.verbose, ignored)
    _report(project_root, options.mode, options.verbose, ignored)
    return EXIT_PASSED


# ---------------------------------------------------------------------------
# The wrapper's run
# ---------------------------------------------------------------------------

MODULE: Final = "datrix_scripts.metrics.complexity"
WRAPPER: Final = "complexity"
MODE_CHECK: Final = "check"
MODE_CC: Final = "cc"
MODE_RAW: Final = "raw"
MODE_HALSTEAD: Final = "halstead"
MODE_MI: Final = "mi"
MODES: Final = (MODE_CHECK, MODE_CC, MODE_RAW, MODE_HALSTEAD, MODE_MI)
DEFAULT_LLM_TIMEOUT_SECONDS: Final = 180
EXIT_LLM_UNAVAILABLE: Final = 2
_FILES_SEPARATOR: Final = ","
#: datrix-common's builtin object tables are generated data: a file under both segments is never checked.
_COMMON_PACKAGE: Final = "datrix-common"
_COMMON_IGNORED_PATHS: Final = ("builtins", "objects")
_NO_IGNORED_PATHS: Final[tuple[str, ...]] = ()

FIX_NEEDS_CHECK: Final = "ERROR: -Fix/-FixAll can only be used with -Mode check (the default)."
TEST_NEEDS_FIX: Final = "ERROR: -Test can only be used with -Fix/-FixAll."
FILES_ALONE: Final = (
    "ERROR: -Files runs mode=check on the named files only; drop -Fix/-FixAll, -Mode, -All and project names."
)

USAGE_LINES: Final = (
    "Usage:",
    " .\\complexity.ps1 <project-name> [options]",
    " .\\complexity.ps1 <folder-path> [options]",
    " .\\complexity.ps1 -All [options]",
    "",
    "Examples:",
    " .\\complexity.ps1 datrix-common",
    " .\\complexity.ps1 datrix-common -Mode raw",
    " .\\complexity.ps1 -All -Mode halstead",
    " .\\complexity.ps1 datrix-language -Mode check -Max 10",
    " .\\complexity.ps1 datrix-common -Mode mi -VerboseOutput",
    "",
    "Parameters:",
    " -Mode check | cc | raw | halstead | mi (default: check)",
    " -Max Max cyclomatic and cognitive complexity for mode=check (default: 15)",
    " -Fix Fix worst violation via a local model (mode=check only)",
    " -FixAll Fix ALL violations (implies -Fix), continue after each success",
    " -Test Run pytest after fix; revert if tests fail (use with -Fix/-FixAll)",
    " -MaxRetries Max model attempts per violation (default: 3, use with -Fix)",
    " -LocalMachines Machines to search for model servers (default: shared list)",
    " -Model Models for fixes, best first (default: any model in memory)",
    " -LlmNumPredict Max generated tokens per attempt (default: 4096)",
    " -MaxContextChars Max file-context chars per prompt (default: 8000)",
    " -All Run for all datrix-* projects",
    " -StopOnError Stop on first project failure",
    " -VerboseOutput Verbose output from the check script",
    " -Dbg Debug output",
)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/complexity.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Radon metrics (complexity, raw, Halstead, MI) for one or more Datrix projects, or named files.",
        allow_abbrev=False,
    )
    add_project_arguments(parser)
    parser.add_argument(
        "--mode", choices=MODES, default=MODE_CHECK, help="check (enforce --max), cc, raw, halstead, mi (default: check)."
    )
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX_COMPLEXITY,
        metavar="N",
        help=f"Max cyclomatic and cognitive complexity for mode=check (default: {DEFAULT_MAX_COMPLEXITY}).",
    )
    parser.add_argument(
        "--files",
        action="append",
        default=[],
        metavar="A.py[,B.py]",
        help="Check exactly these .py files (mode=check); repeatable, each a comma-separated list.",
    )
    parser.add_argument("--fix", action="store_true", help="Fix the worst violation with a local model (mode=check).")
    parser.add_argument("--fix-all", action="store_true", help="Fix every violation, worst first. Implies --fix.")
    parser.add_argument("--test", action="store_true", help="Run pytest after each fix; revert if it fails (--fix).")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=MAX_FIX_RETRIES,
        metavar="N",
        help=f"Max model attempts per violation (default: {MAX_FIX_RETRIES}).",
    )
    add_wrapper_llm_arguments(parser, timeout_seconds=DEFAULT_LLM_TIMEOUT_SECONDS, model_flag="--model")
    parser.add_argument(
        "--llm-num-predict",
        type=int,
        default=DEFAULT_COMPLEXITY_LLM_NUM_PREDICT,
        metavar="N",
        help=f"Max generated tokens per refactor attempt (default: {DEFAULT_COMPLEXITY_LLM_NUM_PREDICT}).",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=DEFAULT_COMPLEXITY_LLM_TEMPERATURE,
        metavar="FLOAT",
        help=f"Sampling temperature (default: {DEFAULT_COMPLEXITY_LLM_TEMPERATURE}).",
    )
    parser.add_argument(
        "--max-context-chars",
        type=int,
        default=DEFAULT_COMPLEXITY_CONTEXT_CHARS,
        metavar="N",
        help=(
            "Maximum file-context characters in each prompt; the target function is always sent in full "
            f"(default: {DEFAULT_COMPLEXITY_CONTEXT_CHARS})."
        ),
    )
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on the first project that fails.")
    parser.add_argument("--verbose-output", action="store_true", help="Name each file as it is analyzed.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="As --verbose-output, at DEBUG.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted packages.")
    return parser


def requested_files(args: argparse.Namespace) -> list[str]:
    """The ``--files`` paths: each value split on commas (``powershell -File`` passes ``a,b`` as one), trimmed."""
    return [part.strip() for raw in args.files for part in raw.split(_FILES_SEPARATOR) if part.strip()]


def _refusal(args: argparse.Namespace, files: Sequence[str]) -> list[str]:
    """The line refusing a combination of options (empty when the combination runs)."""
    fix = args.fix or args.fix_all
    if fix and args.mode != MODE_CHECK:
        return [FIX_NEEDS_CHECK]
    if args.test and not fix:
        return [TEST_NEEDS_FIX]
    named_projects = [*args.positional_projects, *args.projects]
    if files and (fix or args.mode != MODE_CHECK or args.all or named_projects):
        return [FILES_ALONE]
    return []


def _analysis_options(args: argparse.Namespace) -> AnalysisOptions:
    fix = None
    if args.fix or args.fix_all:
        fix = FixOptions(
            fix_all=args.fix_all,
            unit_tests=args.test,
            max_retries=args.max_retries,
            num_predict=args.llm_num_predict,
            temperature=args.llm_temperature,
            max_context_chars=args.max_context_chars,
            llm_settings=wrapper_llm_settings(args),
        )
    return AnalysisOptions(
        mode=args.mode, max_complexity=args.max, verbose=args.verbose_output or args.debug, fix=fix
    )


def _ignored_paths(project: str) -> tuple[str, ...]:
    return _COMMON_IGNORED_PATHS if project == _COMMON_PACKAGE else _NO_IGNORED_PATHS


def _run_files(files: Sequence[str], max_complexity: int) -> int:
    print(f"Running complexity (mode=check) for {len(files)} file(s)")
    code = check_files([Path(name) for name in files], max_complexity)
    if code == EXIT_PASSED:
        print(f"[PASS] Complexity (check) passed for {len(files)} file(s)")
    else:
        print(f"[FAIL] Complexity (check) failed (exit code: {code})")
    return code


def _run_projects(args: argparse.Namespace, workspace: Path) -> int:
    try:
        projects = select_projects(args, workspace, usage=USAGE_LINES, wording=CODE_SHAPE_WORDING)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    scope = "all projects" if args.all else "projects"
    print(f"Running complexity (mode={args.mode}) for {scope}: {', '.join(projects)}")
    options = _analysis_options(args)

    def run_one(project: str) -> int:
        code = analyze_project(workspace / project, options, _ignored_paths(project))
        print("")
        if code != EXIT_PASSED:
            print(f"[FAIL] Complexity ({args.mode}) failed for {project} (exit code: {code})")
        elif options.fix is not None:
            print(f"[DONE] Complexity fix operation completed for {project}")
        else:
            print(f"[PASS] Complexity ({args.mode}) passed for {project}")
        return code

    results = run_projects(
        projects, run_one, stop_on_error=args.stop_on_error, banner_info=f"mode={args.mode}", stop_message=STOP_MESSAGE_FLAG
    )
    title = f"Complexity Summary (mode={args.mode})"
    if options.fix is not None:
        return print_summary(
            title, results, framed=True, pass_label=DONE_LABEL, count_label=COMPLETED_COUNT_LABEL, total=len(projects)
        )
    return print_summary(title, results, framed=True, total=len(projects))


def run_complexity(args: argparse.Namespace, workspace: Path) -> int:
    """The wrapper's run over *workspace*: refuse a bad combination, then the named files or the projects."""
    files = requested_files(args)
    refusal = _refusal(args, files)
    if refusal:
        for line in refusal:
            print(line)
        return EXIT_FAILED
    if files:
        return _run_files(files, args.max)
    return _run_projects(args, workspace)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_NESTED_BODY: Final = (
    "def tangled(values: list[int]) -> int:\n"
    "    total = 0\n"
    "    for value in values:\n"
    "        if value > 0:\n"
    "            for other in values:\n"
    "                if other > value:\n"
    "                    if other % 2:\n"
    "                        total += 1\n"
    "                    elif other % 3:\n"
    "                        total -= 1\n"
    "    return total\n"
)
_FLAT_BODY: Final = "def flat(value: int) -> int:\n    return value + 1\n"
_TIGHT_MAX: Final = "--max=3"


def _printed_by_run(argv: Sequence[str], workspace: Path) -> tuple[int, list[str], list[str]]:
    """The exit code of ``run_complexity`` on *argv* over *workspace*, and the lines it printed to stdout and
    to stderr."""
    printed = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(errors):
        code = run_complexity(build_parser().parse_args(list(argv)), workspace)
    return code, printed.getvalue().splitlines(), errors.getvalue().splitlines()


def _planted(root: Path) -> Path:
    workspace = plant_workspace(root)
    write_files(workspace, {"datrix-a/src/tangled.py": _NESTED_BODY, "datrix-b/src/flat.py": _FLAT_BODY})
    return workspace


def _check_refused_combinations_exit_one() -> None:
    cases = (
        (["datrix-a", "--fix", "--mode=raw"], FIX_NEEDS_CHECK),
        (["datrix-a", "--fix-all", "--mode=mi"], FIX_NEEDS_CHECK),
        (["datrix-a", "--test"], TEST_NEEDS_FIX),
        (["--all", "--files=a.py"], FILES_ALONE),
        (["datrix-a", "--files=a.py"], FILES_ALONE),
        (["--files=a.py", "--mode=cc"], FILES_ALONE),
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = plant_workspace(Path(tmp))
        for argv, line in cases:
            code, lines, _ = _printed_by_run(argv, workspace)
            assert (code, lines) == (EXIT_FAILED, [line]), (argv, code, lines)


def _check_nothing_given_prints_usage_and_available() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines, _ = _printed_by_run([], plant_workspace(Path(tmp)))
    expected = [
        "", "ERROR: No projects specified.", "", *USAGE_LINES, "", "Available projects:", " - datrix-a", " - datrix-b", ""
    ]
    assert (code, lines) == (EXIT_FAILED, expected), (code, lines)


def _check_a_violation_fails_its_project_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines, errors = _printed_by_run(["datrix-a", "datrix-b", _TIGHT_MAX], _planted(Path(tmp)))
    assert code == EXIT_FAILED, (code, lines, errors)
    assert "[FAIL] Complexity (check) failed for datrix-a (exit code: 1)" in lines, lines
    assert "[PASS] Complexity (check) passed for datrix-b" in lines, lines
    assert [line for line in errors if line.endswith(":1 tangled (cyclomatic=7)")], errors
    assert [line for line in errors if line.endswith(":1 tangled (cognitive=19)")], errors
    assert lines[-4:] == [" [FAIL] : datrix-a", " [PASS] : datrix-b", "", "Total: 2 | Passed: 1 | Failed: 1"], lines


def _check_files_checks_the_named_files_split_on_commas() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = _planted(Path(tmp))
        tangled = workspace / "datrix-a" / "src" / "tangled.py"
        flat = workspace / "datrix-b" / "src" / "flat.py"
        failed, failed_lines, _ = _printed_by_run([f"--files={tangled},{flat}", _TIGHT_MAX], workspace)
        passed, passed_lines, passed_errors = _printed_by_run([f"--files={flat}", _TIGHT_MAX], workspace)
    assert (failed, failed_lines) == (
        EXIT_FAILED,
        ["Running complexity (mode=check) for 2 file(s)", "[FAIL] Complexity (check) failed (exit code: 1)"],
    ), (failed, failed_lines)
    assert (passed, passed_lines) == (
        EXIT_PASSED,
        ["Running complexity (mode=check) for 1 file(s)", "[PASS] Complexity (check) passed for 1 file(s)"],
    ), (passed, passed_lines)
    assert passed_errors == ["1 file(s): 0 cyclomatic and 0 cognitive violation(s) above 3."], passed_errors


def _check_a_report_mode_passes_whatever_the_complexity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines, _ = _printed_by_run(["datrix-a", "--mode=cc", _TIGHT_MAX], _planted(Path(tmp)))
    assert code == EXIT_PASSED, (code, lines)
    assert [line for line in lines if line.endswith(":1 tangled (complexity=7)")], lines
    assert lines[-1] == "Total: 1 | Passed: 1 | Failed: 0", lines


def _check_only_common_skips_its_builtin_object_tables() -> None:
    assert _ignored_paths(_COMMON_PACKAGE) == _COMMON_IGNORED_PATHS
    assert _ignored_paths("datrix-a") == _NO_IGNORED_PATHS


_SELF_TEST_CHECKS: Final = (
    _check_refused_combinations_exit_one,
    _check_nothing_given_prints_usage_and_available,
    _check_a_violation_fails_its_project_only,
    _check_files_checks_the_named_files_split_on_commas,
    _check_a_report_mode_passes_whatever_the_complexity,
    _check_only_common_skips_its_builtin_object_tables,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    line_buffered_stdout()
    return run_complexity(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
