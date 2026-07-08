#!/usr/bin/env python3
"""
Detect and score error message quality in a Datrix project's src tree.

Modes:
    check  - Enforce minimum quality score; exit 1 if any error site scores below --min-score.
    report - List all error sites with quality scores (informational, always exit 0).

Only analyzes Python files under project_root/src; tests are excluded by default.
Uses AST-based detection (ast.parse + ast.walk) — no regex on source code.

Usage:
    python error_messages.py --project-root D:\\datrix\\datrix-common --mode check --min-score 2
    python error_messages.py --project-root D:\\datrix\\datrix-common --mode report
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Add library root to sys.path for shared imports
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.ollama_utils import (  # noqa: E402
    OLLAMA_DEFAULT_MODEL,
    OLLAMA_DEFAULT_URL,
    OLLAMA_MAX_FIX_RETRIES,
    apply_and_verify_on_disk as _apply_and_verify_on_disk_shared,
    build_retry_feedback as _build_retry_feedback_shared,
    call_ollama as _call_ollama_shared,
    parse_ollama_response as _parse_ollama_response_shared,
)

logger = logging.getLogger(__name__)

DEFAULT_MIN_SCORE = 2
DEFAULT_IGNORE_DIRS = ("tests", "test", "__pycache__", ".git")

# Blocks excluded from scoring (path_substring, function_name).
# A site is excluded when the file path contains the first element AND the
# enclosing function name matches the second element exactly.
#
# Categories:
#   logging-only       — logger.error/warning diagnostics, not user-facing raises
#   internal-assertion — internal consistency checks in private/framework code
#   impossible-state   — defensive guards that should never execute
#   re-raise-wrapper   — raise … from e where the original exception already has context
#   framework-boundary — Pydantic validators / __init_subclass__ / protocol enforcement
#   testing            — test-infrastructure assertions (not production code)
EXCLUDED_ERROR_SITES: list[tuple[str, str]] = [
    # ── logging-only — internal diagnostic messages, not user-facing raises ──────
    ("datrix_cli/commands/factory.py", "wrapped"),
    ("datrix_cli/commands/validate.py", "_validate_file"),
    ("datrix_cli/main.py", "<module>"),
    ("datrix_cli/utils.py", "ensure_datrix_files"),
    ("datrix_codegen_aws/generators/aws_generator.py", "_get_fargate_cpu"),
    ("datrix_codegen_aws/generators/aws_generator.py", "_get_fargate_memory"),
    ("datrix_codegen_aws/generators/aws_generator.py", "_get_desired_count"),
    ("datrix_codegen_common/algorithms/migration_cqrs.py", "resolve_cqrs_rdbms_block_name"),
    ("datrix_codegen_common/orchestration/seed_orchestrator.py", "_validate_and_process_block"),
    ("datrix_codegen_docker/generators/compose/compose_builder.py", "_apply_deployment_to_entry"),
    ("datrix_codegen_python/generators/entity/_entity_relationships.py", "_resolve_child_fk_column"),
    ("datrix_codegen_python/hooks/language_hooks.py", "format_files"),
    ("datrix_codegen_sql/migration/renderer.py", "_warn_non_nullable_add"),
    ("datrix_codegen_typescript/language_hooks.py", "validate_files"),
    ("datrix_common/config/env_ref_scan.py", "_log_attr_access_failure"),
    ("datrix_common/generation/audit_log.py", "write_audit_log"),
    ("datrix_common/generation/pipeline.py", "_validate_type_completeness"),
    ("datrix_common/generation/snapshot.py", "load_latest_snapshot"),
    ("datrix_common/plugin/registry.py", "_load_classes_from_entry_points"),
    ("datrix_common/utils/engine_helpers.py", "resolve_default_dialect_for_app"),
    # ── internal-assertion — guards on internal invariants, not user input ────────
    ("datrix_cli/commands/factory.py", "command_wrapper"),
    ("datrix_cli/commands/generators.py", "_get_pypi_latest_version"),
    ("datrix_cli/linter/rule_factory.py", "__init__"),
    ("datrix_codegen_common/algorithms/python_service_constants.py", "_interpolation_expr"),
    ("datrix_codegen_common/transpiler/syntax_emitters.py", "emit_fstring"),
    ("datrix_codegen_common/transpiler/syntax_emitters.py", "emit_variable_decl"),
    ("datrix_codegen_python/transpiler/visitor_expressions.py", "_transpile_dispatched_call"),
    ("datrix_codegen_python/transpiler/visitor_expressions.py", "_transpile_emitted_call"),
    ("datrix_codegen_python/transpiler/visitor_expressions.py", "_transpile_throws_call"),
    ("datrix_codegen_typescript/transpiler/visitor_expressions.py", "_transpile_dispatched_spec_call"),
    ("datrix_codegen_typescript/transpiler/visitor_expressions.py", "_transpile_emitted_spec_call"),
    ("datrix_codegen_typescript/transpiler/visitor_expressions.py", "_transpile_throws_spec_call"),
    ("datrix_codegen_typescript/transpiler/visitor_expressions.py", "_transpile_format_date_call"),
    ("datrix_codegen_typescript/transpiler/visitor_statements.py", "_handle_cache_call"),
    ("datrix_codegen_docker/generators/compose/_compose_infra.py", "_build_rabbitmq_queue"),
    ("datrix_codegen_docker/generators/config/gateway_generator.py", "build_gateway_container"),
    ("datrix_codegen_docker/generators/infra/dashboard_builder.py", "generate_dashboards"),
    ("datrix_codegen_python/generators/api/_api_test_http_samples.py", "_handler_body_has_not_found_on_miss_lookup"),
    ("datrix_codegen_python/generators/api/gateway_generator.py", "_generate_gateway_auth"),
    ("datrix_codegen_python/generators/api/gateway_generator.py", "_generate_gateway_transforms"),
    ("datrix_codegen_python/generators/cross_cutting/integration_generator.py", "_generate_email_client"),
    ("datrix_codegen_python/generators/persistence/nosql_connection_generator.py", "_get_primary_key_context"),
    ("datrix_codegen_python/generators/persistence/seed_generator.py", "_parse_seed_yaml"),
    ("datrix_codegen_python/generators/service/dev_scripts_generator.py", "_derive_project_name_from_app"),
    ("datrix_codegen_python/micro_generators/integration.py", "render_email"),
    ("datrix_codegen_sql/constraint_builder.py", "build_primary_key_constraint"),
    ("datrix_codegen_typescript/generators/entity/constant_generator.py", "_interpolation_expr"),
    ("datrix_codegen_typescript/generators/cross_cutting/integration_generator.py", "_generate_email_service"),
    ("datrix_codegen_typescript/generators/messaging/pubsub_connection_generator.py", "_generate_block"),
    ("datrix_codegen_typescript/generators/persistence/nosql_connection_generator.py", "_get_primary_key_context"),
    ("datrix_codegen_typescript/micro_generators/pubsub_connection.py", "render"),
    ("datrix_common/datrix_model/_meta.py", "_make_require_method"),
    ("datrix_common/datrix_model/base.py", "_register_named"),
    ("datrix_common/generation/language_generator.py", "generate"),
    ("datrix_common/testing/names.py", "unique_name"),
    ("datrix_common/transpiler/base.py", "decrease_indent"),
    ("datrix_common/transpiler/resolution.py", "pop"),
    ("datrix_common/transpiler/resolution.py", "declare"),
    ("datrix_common/transpiler/resolution.py", "add_substitution"),
    # ── impossible-state — exhaustive branch guards, should never execute ─────────
    ("datrix_codegen_typescript/transpiler/core.py", "emit_resolved_identifier"),
    ("datrix_common/datrix_model/base.py", "container"),
    ("datrix_common/generation/pipeline.py", "_run_stage"),
    ("datrix_common/infra/registry.py", "_build_container_key_impl"),
    # ── re-raise-wrapper — raise … from e, wrapping with context ─────────────────
    ("datrix_common/fileops/writer.py", "write"),
    ("datrix_common/generation/formatter.py", "_format_json_file"),
    # ── framework-boundary — Pydantic validators, framework-enforced constraints ─
    ("datrix_common/config/datasource/models.py", "_validate_external_platform_fields"),
    ("datrix_common/config/datasource/models.py", "_engine_requirements"),
    ("datrix_common/config/datasource/models.py", "_url_or_host_port"),
    ("datrix_common/config/datasource/models.py", "_validate_platform_fields"),
    ("datrix_common/config/serverless/models.py", "_validate_handler_entry"),
    ("datrix_common/config/storage/models.py", "_provider_requirements"),
    ("datrix_common/generation/snapshot.py", "_validate_app_state"),
    ("datrix_common/generation/snapshot.py", "_validate_entity_fields"),
    ("datrix_common/generation/snapshot.py", "_validate_service_entities"),
    ("datrix_common/generation/snapshot.py", "_validate_snapshot_schema"),
    # ── testing — test-infrastructure assertions ─────────────────────────────────
    ("datrix_codegen_python/testing.py", "_check_ruff_f821"),
    ("datrix_codegen_typescript/testing.py", "assert_all_ts_files_balanced"),
    ("datrix_common/testing/assertions.py", "assert_file_exists"),
    ("datrix_common/testing/assertions.py", "assert_json_valid"),
    ("datrix_common/testing/assertions.py", "assert_balanced_braces"),
]

# --- Scoring keyword lists ---

_EXPECTED_KEYWORDS = (
    "expected",
    "must be",
    "should be",
    "valid",
    "required",
    "allowed",
    "range",
    "between",
)

_OPTIONS_KEYWORDS = (
    "available",
    "valid:",
    "options:",
    "choices:",
    "one of",
    "supported:",
)

_FIX_KEYWORDS = (
    "try",
    "use",
    "instead",
    "install",
    "run",
    "check",
    "ensure",
    "did you mean",
    "suggestion",
)


# --- Data classes ---


@dataclass
class MessageScore:
    """Score breakdown for a single error message against the 4-criterion heuristic."""

    total: int
    has_what_went_wrong: bool
    has_expected: bool
    has_valid_options: bool
    has_fix_suggestion: bool
    missing: list[str] = field(default_factory=list)


@dataclass
class ErrorSite:
    """A single error site detected in the codebase."""

    file_path: Path
    line_number: int
    function_name: str | None
    class_name: str | None
    exception_type: str | None
    message_text: str | None
    has_suggestions_kwarg: bool
    is_logging: bool
    score: MessageScore | None = None
    excluded: bool = False


# --- Detection ---


def _is_excluded_site(file_path: Path, func_name: str | None) -> bool:
    """Check whether a site matches the exclusion list."""
    if not func_name:
        return False
    rel_path_norm = str(file_path).replace("\\", "/")
    return any(
        path_part in rel_path_norm and func_name == excluded_func
        for path_part, excluded_func in EXCLUDED_ERROR_SITES
    )


def collect_error_sites(
    project_root: Path,
    ignore_path_contains_all: list[str] | None = None,
) -> list[ErrorSite]:
    """Walk src/ tree, parse each .py file, collect raise/log.error/print-stderr sites.

    Args:
        project_root: Path to the project root (containing src/).
        ignore_path_contains_all: If provided, skip files whose path parts contain
            ALL listed segments (e.g. ["builtins", "objects"] skips
            src/pkg/builtins/objects/...).
    """
    src = project_root / "src"
    if not src.is_dir():
        return []

    sites: list[ErrorSite] = []
    for py_path in sorted(src.rglob("*.py")):
        parts = py_path.relative_to(src).parts
        # Skip standard ignore dirs
        if any(part in DEFAULT_IGNORE_DIRS for part in parts):
            continue
        # Skip paths containing all listed segments
        if ignore_path_contains_all and all(
            seg in parts for seg in ignore_path_contains_all
        ):
            continue
        # Skip test files
        rel_str = str(py_path).replace("\\", "/")
        if "/tests/" in rel_str or "/test/" in rel_str:
            continue
        try:
            source = py_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(py_path))
        except SyntaxError:
            continue
        file_sites = _walk_ast_for_errors(tree, py_path)
        sites.extend(file_sites)

    return sites


def _walk_ast_for_errors(tree: ast.Module, file_path: Path) -> list[ErrorSite]:
    """AST visitor that collects error sites from a single file."""
    sites: list[ErrorSite] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            site = _process_raise(node, tree, file_path)
            if site is not None:
                sites.append(site)
        elif isinstance(node, ast.Call):
            site = _process_call(node, tree, file_path)
            if site is not None:
                sites.append(site)

    return sites


def _process_raise(
    node: ast.Raise, tree: ast.Module, file_path: Path
) -> ErrorSite | None:
    """Process a raise statement and return an ErrorSite if it should be scored."""
    # Skip bare re-raise (`raise` without arguments)
    if node.exc is None:
        return None

    # Skip re-raise with `from` that references an existing exception variable
    # (pattern: `raise X(...) from e` where e is a caught exception — still score the message)
    # We only skip bare `raise` (above).

    exc_node = node.exc
    exception_type: str | None = None
    message_text: str | None = None
    has_suggestions_kwarg = False

    if isinstance(exc_node, ast.Call):
        # raise SomeException("message")
        exception_type = _get_exception_type_name(exc_node.func)

        # Skip NotImplementedError
        if exception_type == "NotImplementedError":
            return None

        # Extract message from first positional argument
        if exc_node.args:
            message_text = _extract_message_text(exc_node.args[0])

        # Check for suggestions= keyword argument
        for kw in exc_node.keywords:
            if kw.arg == "suggestions":
                has_suggestions_kwarg = True
                break
    elif isinstance(exc_node, ast.Name):
        # raise some_variable (re-raise of caught exception)
        return None
    else:
        # raise SomeException (no call, just the class) — rare, skip
        return None

    func_name = _get_function_context(tree, node.lineno)
    class_name = _get_class_context(tree, node.lineno)
    is_excluded = _is_excluded_site(file_path, func_name)

    return ErrorSite(
        file_path=file_path,
        line_number=node.lineno,
        function_name=func_name,
        class_name=class_name,
        exception_type=exception_type,
        message_text=message_text,
        has_suggestions_kwarg=has_suggestions_kwarg,
        is_logging=False,
        excluded=is_excluded,
    )


def _process_call(
    node: ast.Call, tree: ast.Module, file_path: Path
) -> ErrorSite | None:
    """Process a function call that may be logging.error/warning or print to stderr."""
    # Check for logging.error() / logging.warning() / logger.error() / logger.warning()
    if isinstance(node.func, ast.Attribute) and node.func.attr in (
        "error",
        "warning",
    ):
        # Verify it looks like a logger call
        if isinstance(node.func.value, ast.Name):
            caller_name = node.func.value.id
            if caller_name in ("logging", "logger", "log", "self"):
                return _build_logging_site(node, tree, file_path)
        elif isinstance(node.func.value, ast.Attribute):
            # self.logger.error() or module.logger.error()
            if isinstance(node.func.value, ast.Attribute) and node.func.value.attr in (
                "logger",
                "log",
            ):
                return _build_logging_site(node, tree, file_path)

    # Check for print(..., file=sys.stderr)
    if isinstance(node.func, ast.Name) and node.func.id == "print":
        for kw in node.keywords:
            if kw.arg == "file" and _is_sys_stderr(kw.value):
                return _build_print_stderr_site(node, tree, file_path)

    return None


def _build_logging_site(
    node: ast.Call, tree: ast.Module, file_path: Path
) -> ErrorSite:
    """Build an ErrorSite for a logging.error/warning call."""
    message_text: str | None = None
    if node.args:
        message_text = _extract_message_text(node.args[0])

    func_name = _get_function_context(tree, node.lineno)
    class_name = _get_class_context(tree, node.lineno)
    is_excluded = _is_excluded_site(file_path, func_name)

    return ErrorSite(
        file_path=file_path,
        line_number=node.lineno,
        function_name=func_name,
        class_name=class_name,
        exception_type=None,
        message_text=message_text,
        has_suggestions_kwarg=False,
        is_logging=True,
        excluded=is_excluded,
    )


def _build_print_stderr_site(
    node: ast.Call, tree: ast.Module, file_path: Path
) -> ErrorSite:
    """Build an ErrorSite for a print(..., file=sys.stderr) call."""
    message_text: str | None = None
    if node.args:
        message_text = _extract_message_text(node.args[0])

    func_name = _get_function_context(tree, node.lineno)
    class_name = _get_class_context(tree, node.lineno)
    is_excluded = _is_excluded_site(file_path, func_name)

    return ErrorSite(
        file_path=file_path,
        line_number=node.lineno,
        function_name=func_name,
        class_name=class_name,
        exception_type=None,
        message_text=message_text,
        has_suggestions_kwarg=False,
        is_logging=False,
        excluded=is_excluded,
    )


def _is_sys_stderr(node: ast.expr) -> bool:
    """Check if a node is `sys.stderr`."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
        and node.attr == "stderr"
    )


def _get_exception_type_name(node: ast.expr) -> str | None:
    """Extract exception class name from a Call node's func."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_message_text(node: ast.expr) -> str | None:
    """Extract message string from AST node (string, f-string, concatenation, .format())."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    if isinstance(node, ast.JoinedStr):
        # f-string: reconstruct with {placeholders}
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("{...}")
            else:
                parts.append("{...}")
        return "".join(parts)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        # String concatenation: "a" + "b"
        left = _extract_message_text(node.left)
        right = _extract_message_text(node.right)
        if left is not None and right is not None:
            return left + right
        if left is not None:
            return left + "{...}"
        if right is not None:
            return "{...}" + right
        return None

    if isinstance(node, ast.Call):
        # "...".format(...) pattern
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
        ):
            return node.func.value.value
        return None

    # If it's a plain variable reference, we can't extract the message statically
    return None


def _get_function_context(tree: ast.Module, lineno: int) -> str | None:
    """Find the enclosing function/method name for a given line number."""
    best: str | None = None
    best_start = -1

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_lineno = node.end_lineno if node.end_lineno is not None else node.lineno
            if node.lineno <= lineno <= end_lineno:
                if node.lineno > best_start:
                    best = node.name
                    best_start = node.lineno

    return best


def _get_class_context(tree: ast.Module, lineno: int) -> str | None:
    """Find the enclosing class name for a given line number."""
    best: str | None = None
    best_start = -1

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            end_lineno = node.end_lineno if node.end_lineno is not None else node.lineno
            if node.lineno <= lineno <= end_lineno:
                if node.lineno > best_start:
                    best = node.name
                    best_start = node.lineno

    return best


# --- Scoring ---


def score_message(message: str, has_suggestions_kwarg: bool = False) -> MessageScore:
    """Score a message against the 4-criterion heuristic. Returns MessageScore with breakdown."""
    msg_lower = message.lower()
    total = 0
    missing: list[str] = []

    # Criterion 1: What went wrong
    # Message length >= 20 chars AND contains variable reference
    has_what_went_wrong = len(message) >= 20 and _has_variable_reference(message)
    if has_what_went_wrong:
        total += 1
    else:
        missing.append("what-went-wrong")

    # Criterion 2: What was expected
    has_expected = any(kw in msg_lower for kw in _EXPECTED_KEYWORDS)
    if has_expected:
        total += 1
    else:
        missing.append("expected")

    # Criterion 3: Valid options
    has_valid_options = any(kw in msg_lower for kw in _OPTIONS_KEYWORDS) or _has_list_literal(
        message
    )
    if has_valid_options:
        total += 1
    else:
        missing.append("options")

    # Criterion 4: Fix suggestions
    has_fix_suggestion = has_suggestions_kwarg or any(
        kw in msg_lower for kw in _FIX_KEYWORDS
    )
    if has_fix_suggestion:
        total += 1
    else:
        missing.append("fix")

    return MessageScore(
        total=total,
        has_what_went_wrong=has_what_went_wrong,
        has_expected=has_expected,
        has_valid_options=has_valid_options,
        has_fix_suggestion=has_fix_suggestion,
        missing=missing,
    )


def _has_variable_reference(message: str) -> bool:
    """Check if message contains a variable reference (f-string interpolation or format placeholder)."""
    return "{" in message


def _has_list_literal(message: str) -> bool:
    """Check if message contains a list/set literal pattern like [...] or {...}."""
    # Look for patterns like [a, b, c] or {a, b, c} that indicate enumerated values
    # We check for brackets/braces that contain comma-separated items
    if "[" in message and "]" in message:
        start = message.index("[")
        end = message.index("]", start)
        content = message[start + 1 : end]
        if "," in content:
            return True
    return False


# --- Reporting ---


def run_check(
    project_root: Path,
    min_score: int = DEFAULT_MIN_SCORE,
    ignore_path_contains_all: list[str] | None = None,
    show_excluded: bool = False,
) -> int:
    """Enforce minimum quality score. Returns exit code (0=pass, 1=violations found)."""
    sites = collect_error_sites(project_root, ignore_path_contains_all)

    # Score all sites (including excluded, for --show-excluded)
    violations: list[ErrorSite] = []
    excluded_violations: list[ErrorSite] = []
    for site in sites:
        if site.message_text is None:
            # Cannot score dynamically-composed messages — skip
            continue
        site.score = score_message(site.message_text, site.has_suggestions_kwarg)
        if site.score.total < min_score:
            if site.excluded:
                excluded_violations.append(site)
            else:
                violations.append(site)

    if show_excluded and excluded_violations:
        excluded_violations.sort(key=lambda s: (str(s.file_path), s.line_number))
        print(
            f"Excluded sites ({len(excluded_violations)}):",
            file=sys.stderr,
        )
        for site in excluded_violations:
            assert site.score is not None
            func_display = site.function_name or "<module>"
            print(
                f"  {site.file_path}:{site.line_number} {func_display} "
                f"(score={site.score.total}/4) [excluded]",
                file=sys.stderr,
            )

    if not violations:
        print(
            f"Error message quality: all messages meet minimum score {min_score}.",
            file=sys.stderr,
        )
        return 0

    # Sort deterministically by file path then line number
    violations.sort(key=lambda s: (str(s.file_path), s.line_number))

    print(
        f"Error message quality: {len(violations)} message(s) below minimum score {min_score}:",
        file=sys.stderr,
    )
    for site in violations:
        assert site.score is not None
        func_display = site.function_name or "<module>"
        missing_str = ", ".join(site.score.missing)
        print(
            f"  {site.file_path}:{site.line_number} {func_display} "
            f"(score={site.score.total}/4, missing: {missing_str})",
            file=sys.stderr,
        )

    return 1


def run_report(
    project_root: Path,
    ignore_path_contains_all: list[str] | None = None,
    show_excluded: bool = False,
) -> int:
    """List all error sites with quality scores. Returns exit code 0."""
    sites = collect_error_sites(project_root, ignore_path_contains_all)

    # Separate excluded sites
    active_sites = [s for s in sites if not s.excluded]
    excluded_sites = [s for s in sites if s.excluded]

    # Score all active sites that have extractable messages
    for site in active_sites:
        if site.message_text is not None:
            site.score = score_message(site.message_text, site.has_suggestions_kwarg)

    # Sort deterministically by file path then line number
    active_sites.sort(key=lambda s: (str(s.file_path), s.line_number))

    for site in active_sites:
        func_display = site.function_name or "<module>"
        score_display = f"score={site.score.total}" if site.score else "score=?"
        exc_display = site.exception_type or ("logging" if site.is_logging else "print-stderr")
        msg_preview = _truncate_message(site.message_text) if site.message_text else "<dynamic>"
        print(
            f"{site.file_path}:{site.line_number} {func_display} "
            f"{score_display} {exc_display}(\"{msg_preview}\")"
        )

    if show_excluded and excluded_sites:
        # Score excluded sites for display
        for site in excluded_sites:
            if site.message_text is not None:
                site.score = score_message(site.message_text, site.has_suggestions_kwarg)
        excluded_sites.sort(key=lambda s: (str(s.file_path), s.line_number))
        print(f"\nExcluded sites ({len(excluded_sites)}):")
        for site in excluded_sites:
            func_display = site.function_name or "<module>"
            score_display = f"score={site.score.total}" if site.score else "score=?"
            exc_display = site.exception_type or ("logging" if site.is_logging else "print-stderr")
            msg_preview = _truncate_message(site.message_text) if site.message_text else "<dynamic>"
            print(
                f"  {site.file_path}:{site.line_number} {func_display} "
                f"{score_display} {exc_display}(\"{msg_preview}\") [excluded]"
            )

    print(f"\nTotal error sites: {len(active_sites)}", file=sys.stderr)
    if excluded_sites:
        print(f"Excluded sites: {len(excluded_sites)}", file=sys.stderr)
    scored = [s for s in active_sites if s.score is not None]
    if scored:
        avg = sum(s.score.total for s in scored if s.score) / len(scored)
        print(f"Average score: {avg:.1f}/4", file=sys.stderr)
        by_score = [0, 0, 0, 0, 0]
        for s in scored:
            assert s.score is not None
            by_score[s.score.total] += 1
        print(
            f"Distribution: 0={by_score[0]} 1={by_score[1]} 2={by_score[2]} "
            f"3={by_score[3]} 4={by_score[4]}",
            file=sys.stderr,
        )

    return 0


def _truncate_message(message: str, max_len: int = 60) -> str:
    """Truncate a message for display, replacing newlines with spaces."""
    msg = message.replace("\n", " ").replace("\r", "")
    if len(msg) > max_len:
        return msg[: max_len - 3] + "..."
    return msg


# --- Ollama fix pipeline ---



def run_fix(
    project_root: Path,
    min_score: int = DEFAULT_MIN_SCORE,
    fix_all: bool = False,
    run_tests: bool = False,
    max_retries: int = OLLAMA_MAX_FIX_RETRIES,
    ollama_url: str = OLLAMA_DEFAULT_URL,
    ollama_model: str = OLLAMA_DEFAULT_MODEL,
    ignore_path_contains_all: list[str] | None = None,
) -> int:
    """Fix error message violations using Ollama. Returns exit code."""
    targets = _collect_fix_targets(project_root, min_score, ignore_path_contains_all)
    if not targets:
        print("No error message violations found. Nothing to fix.", file=sys.stderr)
        return 0

    fixed_count = 0
    failed_count = 0

    for site in targets:
        success = _attempt_fix_error_site(
            site, project_root, max_retries, run_tests, ollama_url, ollama_model,
            min_score,
        )
        if success:
            fixed_count += 1
            if not fix_all:
                print("Re-run the script to fix more violations.", file=sys.stderr)
                return 0
            # Re-collect targets since line numbers shifted
            targets = _collect_fix_targets(
                project_root, min_score, ignore_path_contains_all,
            )
            if not targets:
                break
            # Continue with the next target from the fresh list
            # (we break and re-enter next iteration via the outer logic)
        else:
            failed_count += 1

    if fix_all:
        print(
            f"\nFix-all complete: {fixed_count} fixed, {failed_count} failed.",
            file=sys.stderr,
        )
        return 0 if fixed_count > 0 or failed_count == 0 else 1

    if fixed_count == 0:
        print("No violations could be fixed.", file=sys.stderr)
        return 1
    return 0


def _collect_fix_targets(
    project_root: Path,
    min_score: int,
    ignore_path_contains_all: list[str] | None,
) -> list[ErrorSite]:
    """Collect sites scoring below min_score, sorted worst-first."""
    sites = collect_error_sites(project_root, ignore_path_contains_all)
    targets: list[ErrorSite] = []
    for site in sites:
        if site.excluded:
            continue
        if site.message_text is None:
            continue
        site.score = score_message(site.message_text, site.has_suggestions_kwarg)
        if site.score.total < min_score:
            targets.append(site)
    # Sort worst-first (lowest score first)
    targets.sort(key=lambda s: (s.score.total if s.score else 0, str(s.file_path), s.line_number))
    return targets


def _attempt_fix_error_site(
    site: ErrorSite,
    project_root: Path,
    max_retries: int,
    run_tests: bool,
    ollama_url: str,
    ollama_model: str,
    min_score: int,
) -> bool:
    """Attempt to fix a single error site. Returns True on success."""
    file_path = site.file_path
    try:
        file_content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
        return False

    original_hash = hashlib.sha256(file_content.encode("utf-8")).hexdigest()
    raise_statement = _extract_raise_statement(file_content, site.line_number)
    if not raise_statement:
        print(
            f"  Could not extract raise statement at {file_path}:{site.line_number}",
            file=sys.stderr,
        )
        return False

    assert site.score is not None
    print(
        f"\nFixing: {file_path}:{site.line_number} {site.function_name or '<module>'} "
        f"(score={site.score.total}/4, missing: {', '.join(site.score.missing)})",
        file=sys.stderr,
    )

    retry_feedback: str | None = None
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"  Retry {attempt}/{max_retries}...", file=sys.stderr)
        print(f"  Sending to Ollama ({ollama_model})...", file=sys.stderr)

        fixed_content, error_msg = _attempt_single_fix(
            site, file_content, project_root, ollama_url, ollama_model,
            retry_feedback,
        )

        if fixed_content is None:
            print(f"  Fix attempt failed: {error_msg}", file=sys.stderr)
            if attempt < max_retries:
                retry_feedback = _build_retry_feedback(
                    error_msg or "Unknown error", attempt,
                )
                continue
            print(f"  All {max_retries} attempt(s) failed.", file=sys.stderr)
            return False

        # Validate in-memory
        valid, validation_error = _validate_error_fix_inmemory(
            file_content, fixed_content, site, min_score,
        )
        if not valid:
            print(f"  Validation failed: {validation_error}", file=sys.stderr)
            if attempt < max_retries:
                retry_feedback = _build_retry_feedback(
                    validation_error or "Validation failed", attempt,
                )
                continue
            print(f"  All {max_retries} attempt(s) failed.", file=sys.stderr)
            return False

        # Apply to disk and verify
        disk_ok, disk_error = _apply_and_verify_on_disk(
            file_path, file_content, fixed_content, original_hash,
            project_root, run_tests,
        )
        if not disk_ok:
            if disk_error == "file_modified":
                return False
            print(f"  Disk verification failed: {disk_error}", file=sys.stderr)
            if attempt < max_retries:
                retry_feedback = _build_retry_feedback(disk_error, attempt)
                continue
            print(f"  All {max_retries} attempt(s) failed.", file=sys.stderr)
            return False

        print(
            f"  Fixed: {file_path}:{site.line_number} {site.function_name or '<module>'}",
            file=sys.stderr,
        )
        return True

    return False


def _attempt_single_fix(
    site: ErrorSite,
    file_content: str,
    project_root: Path,
    ollama_url: str,
    ollama_model: str,
    retry_feedback: str | None = None,
) -> tuple[str | None, str | None]:
    """Single Ollama call. Returns (fixed_content, error_message)."""
    raise_statement = _extract_raise_statement(file_content, site.line_number)
    if not raise_statement:
        return None, "Could not extract raise statement"

    # Build context: imports and surrounding function
    file_context = _extract_error_fix_context(file_content, site.line_number)

    system_prompt = _build_error_fix_system_prompt()
    user_prompt = _build_error_fix_user_prompt(
        site, file_context, raise_statement, retry_feedback,
    )

    response = _call_ollama_shared(system_prompt, user_prompt, ollama_url, ollama_model)
    if response is None:
        return None, "Ollama returned no response"

    replacement = _parse_ollama_response_shared(response)
    if replacement is None:
        return None, "Could not parse code from Ollama response"

    # Apply replacement to file content
    fixed_content = _apply_replacement(
        file_content, site.line_number, raise_statement, replacement,
    )
    if fixed_content is None:
        return None, "Could not apply replacement to file content"

    return fixed_content, None


def _build_error_fix_system_prompt() -> str:
    """System prompt for error message improvement."""
    return (
        "You are a Python error message expert. You improve error messages to be more "
        "helpful for developers debugging issues.\n\n"
        "A high-quality error message has 4 elements:\n"
        "1. **What went wrong** — describe the actual problem with specific values "
        "(use f-string interpolation)\n"
        "2. **What was expected** — state the valid/expected condition\n"
        "3. **Valid options** — list available choices, valid values, or acceptable types\n"
        "4. **Fix suggestion** — tell the developer how to fix it\n\n"
        "Rules:\n"
        "- Preserve the original exception type (ValueError stays ValueError, etc.)\n"
        "- Keep all f-string interpolation variables that exist in the original\n"
        "- Do NOT change surrounding code logic — only modify the error message string\n"
        "- Preserve the original indentation exactly\n"
        "- If the raise has a `from` clause, preserve it\n"
        "- Return ONLY the replacement `raise` statement (or `logging.error()`/`logging.warning()` call)\n"
        "- Use f-strings for interpolation\n"
        "- Output inside a single ```python code fence\n"
        "- No explanations outside the code fence\n\n"
        "Examples:\n\n"
        "Before (score 1/4):\n"
        "```python\n"
        'raise ValueError(f"Invalid type: {field_type}")\n'
        "```\n\n"
        "After (score 4/4):\n"
        "```python\n"
        "raise ValueError(\n"
        '    f"Invalid field type \'{field_type}\' for field \'{field_name}\'. "\n'
        '    f"Expected one of: {VALID_FIELD_TYPES}. "\n'
        '    f"Check your .dtrx file for typos or use a supported type."\n'
        ")\n"
        "```\n\n"
        "Before (score 0/4):\n"
        "```python\n"
        'raise RuntimeError("Generation failed")\n'
        "```\n\n"
        "After (score 4/4):\n"
        "```python\n"
        "raise RuntimeError(\n"
        '    f"Code generation failed for entity \'{entity.name}\' in service '
        "'{service.name}'. \"\n"
        '    f"Expected all field types to be mapped. "\n'
        '    f"Unmapped types: {unmapped}. "\n'
        '    f"Add type mappings in TypeRegistry or use a supported type."\n'
        ")\n"
        "```"
    )


def _build_error_fix_user_prompt(
    site: ErrorSite,
    file_context: str,
    raise_statement: str,
    retry_feedback: str | None = None,
) -> str:
    """User prompt with the raise statement + context + what's missing."""
    assert site.score is not None
    parts: list[str] = []

    if retry_feedback:
        parts.append(f"IMPORTANT — Previous attempt feedback:\n{retry_feedback}\n")

    parts.append(
        f"Improve this error message to score higher. "
        f"Current score: {site.score.total}/4. "
        f"Missing criteria: {', '.join(site.score.missing)}.\n"
    )
    parts.append(f"Exception type: {site.exception_type or 'logging call'}")
    parts.append(f"Function: {site.function_name or '<module>'}")
    if site.class_name:
        parts.append(f"Class: {site.class_name}")

    parts.append(f"\nFile context:\n{file_context}")
    parts.append(
        f"\nStatement to improve (return ONLY the replacement):\n"
        f"```python\n{raise_statement}\n```"
    )

    return "\n".join(parts)


def _extract_error_fix_context(file_content: str, line_number: int) -> str:
    """Extract context around the error site for the LLM."""
    lines = file_content.splitlines()
    # Show surrounding function and imports
    sections: list[str] = []

    # Extract imports (first 40 lines or until non-import)
    import_lines: list[str] = []
    for line in lines[:80]:
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            import_lines.append(line)
        elif stripped and not stripped.startswith("#") and import_lines:
            break
    if import_lines:
        sections.append("Imports:\n" + "\n".join(import_lines[:40]))

    # Show surrounding lines (10 before, 10 after the raise)
    start = max(0, line_number - 11)
    end = min(len(lines), line_number + 10)
    context_lines = lines[start:end]
    sections.append(
        f"Surrounding code (lines {start + 1}-{end}):\n"
        + "\n".join(context_lines)
    )

    return "\n\n".join(sections)


def _extract_raise_statement(file_content: str, line_number: int) -> str:
    """Extract the full raise statement (may span multiple lines)."""
    lines = file_content.splitlines()
    if line_number < 1 or line_number > len(lines):
        return ""

    # Start at the given line (1-indexed)
    start_idx = line_number - 1
    first_line = lines[start_idx]

    # Determine the base indentation of the raise line
    base_indent = len(first_line) - len(first_line.lstrip())

    # Collect lines: the raise/logging statement may span multiple lines
    # (parenthesized string, continuation)
    collected: list[str] = [first_line]

    # Count open/close parens to detect multi-line statements
    paren_depth = first_line.count("(") - first_line.count(")")

    idx = start_idx + 1
    while paren_depth > 0 and idx < len(lines):
        line = lines[idx]
        collected.append(line)
        paren_depth += line.count("(") - line.count(")")
        idx += 1

    return "\n".join(collected)


def _apply_replacement(
    file_content: str,
    line_number: int,
    original_statement: str,
    replacement: str,
) -> str | None:
    """Apply the LLM's replacement to the file content."""
    lines = file_content.splitlines(keepends=True)
    original_lines_count = original_statement.count("\n") + 1
    start_idx = line_number - 1

    # Detect indentation of the original raise statement
    original_first_line = file_content.splitlines()[start_idx]
    target_indent = original_first_line[: len(original_first_line) - len(original_first_line.lstrip())]

    # Normalize the replacement indentation to match the original
    replacement_normalized = _normalize_replacement_indent(replacement, target_indent)

    # Ensure replacement ends with newline
    if not replacement_normalized.endswith("\n"):
        replacement_normalized += "\n"

    # Replace the original lines with the new replacement
    end_idx = start_idx + original_lines_count
    new_lines = lines[:start_idx] + [replacement_normalized] + lines[end_idx:]
    return "".join(new_lines)


def _normalize_replacement_indent(code: str, target_indent: str) -> str:
    """Re-indent replacement code to match the target indentation."""
    lines = code.splitlines()
    if not lines:
        return code

    # Detect current base indent from first non-empty line
    current_indent = ""
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            current_indent = line[: len(line) - len(stripped)]
            break

    if current_indent == target_indent:
        return code

    result: list[str] = []
    for line in lines:
        if not line.strip():
            result.append(line)
        elif line.startswith(current_indent):
            result.append(target_indent + line[len(current_indent):])
        else:
            result.append(line)
    return "\n".join(result)


def _validate_error_fix_inmemory(
    original_content: str,
    fixed_content: str,
    site: ErrorSite,
    min_score: int,
) -> tuple[bool, str]:
    """Validate fix: syntax check + re-score to confirm improvement."""
    # 1. Syntax valid
    try:
        ast.parse(fixed_content)
    except SyntaxError as e:
        return False, f"Syntax error in fixed file: {e}"

    # 2. Exception type preserved — re-parse and check
    if site.exception_type:
        # Find the raise at the same location in the fixed content
        try:
            fixed_tree = ast.parse(fixed_content)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        # Walk the fixed AST to find the raise near the original line
        found_type = _find_exception_type_near_line(fixed_tree, site.line_number)
        if found_type and found_type != site.exception_type:
            return False, (
                f"Exception type changed from '{site.exception_type}' to '{found_type}'. "
                f"The exception type must be preserved."
            )

    # 3. Score improved — re-scan the fixed file for the site's raise and score it
    new_score = _rescore_fixed_site(fixed_content, site)
    if new_score is None:
        # Cannot find the raise anymore — might be OK if it was restructured
        return True, ""

    assert site.score is not None
    if new_score.total <= site.score.total:
        return False, (
            f"Score did not improve: was {site.score.total}/4, "
            f"now {new_score.total}/4. Missing: {', '.join(new_score.missing)}"
        )

    return True, ""


def _find_exception_type_near_line(tree: ast.Module, target_line: int) -> str | None:
    """Find exception type of a raise near the target line (within 5 lines)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            if abs(node.lineno - target_line) <= 5:
                if isinstance(node.exc, ast.Call):
                    return _get_exception_type_name(node.exc.func)
    return None


def _rescore_fixed_site(fixed_content: str, site: ErrorSite) -> MessageScore | None:
    """Re-score the error message at the fixed site."""
    try:
        tree = ast.parse(fixed_content)
    except SyntaxError:
        return None

    # Find raise statements near the original line
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            if abs(node.lineno - site.line_number) <= 5:
                if isinstance(node.exc, ast.Call) and node.exc.args:
                    msg = _extract_message_text(node.exc.args[0])
                    if msg is not None:
                        has_suggestions = any(
                            kw.arg == "suggestions" for kw in node.exc.keywords
                        )
                        return score_message(msg, has_suggestions)
        elif isinstance(node, ast.Call):
            # Check for logging calls
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in ("error", "warning")
                and abs(node.lineno - site.line_number) <= 5
            ):
                if node.args:
                    msg = _extract_message_text(node.args[0])
                    if msg is not None:
                        return score_message(msg)
    return None


def _apply_and_verify_on_disk(
    file_path: Path,
    original_content: str,
    fixed_content: str,
    original_hash: str,
    project_root: Path,
    run_tests: bool,
) -> tuple[bool, str]:
    """Write to disk, run ruff check, optionally run pytest. Revert on failure."""
    success, error_details = _apply_and_verify_on_disk_shared(
        file_path, original_content, fixed_content, original_hash,
        project_root, run_tests=run_tests,
    )
    if not success and error_details == "file_modified":
        print(
            f"  File {file_path} was modified during processing, skipping.",
            file=sys.stderr,
        )
    elif not success and error_details == "test_failure":
        print("  Reverting due to test failures.", file=sys.stderr)
    elif not success and error_details:
        print("  Reverting due to ruff errors.", file=sys.stderr)
    return success, error_details


def _build_retry_feedback(error: str, attempt: int) -> str:
    """Build feedback message for retry attempt with error-message-specific guidance."""
    base = _build_retry_feedback_shared(error, attempt, OLLAMA_MAX_FIX_RETRIES)
    return (
        f"{base}\n"
        "Remember:\n"
        "- Return ONLY the replacement raise/log statement\n"
        "- Preserve the exception type exactly\n"
        "- Use f-string interpolation for dynamic values\n"
        "- Include all 4 criteria: what went wrong, expected, options, fix suggestion"
    )


# --- Entry point ---


def main() -> None:
    """Argument parsing and mode dispatch."""
    # Ensure UTF-8 output on Windows (avoids UnicodeEncodeError for non-ASCII in messages)
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(
        description="Error message quality scanner for Datrix projects.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Path to the project root (containing src/).",
    )
    parser.add_argument(
        "--mode",
        choices=("check", "report"),
        default="check",
        help="Mode: check (enforce min score) or report (list all sites). Default: check.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=DEFAULT_MIN_SCORE,
        metavar="N",
        help=f"Minimum score for check mode (0-4). Default: {DEFAULT_MIN_SCORE}.",
    )
    parser.add_argument(
        "--ignore-path-contains",
        type=str,
        default="",
        metavar="SEG1,SEG2",
        help="Comma-separated substrings to exclude from scanning (e.g., builtins,objects).",
    )
    parser.add_argument(
        "--show-excluded",
        action="store_true",
        help="Show sites excluded from scoring (for debugging the exclusion list).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix the worst error message violation using local Ollama.",
    )
    parser.add_argument(
        "--fix-all",
        action="store_true",
        help="Fix ALL violations (not just the first). Implies --fix.",
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

    args = parser.parse_args()
    project_root = args.project_root.resolve()

    if not project_root.is_dir():
        print(
            f"Error: project root is not a directory: {project_root}",
            file=sys.stderr,
        )
        sys.exit(1)

    ignore_path_contains_all: list[str] | None = None
    if args.ignore_path_contains:
        ignore_path_contains_all = [
            s.strip() for s in args.ignore_path_contains.split(",") if s.strip()
        ]

    if args.fix or args.fix_all:
        if args.mode != "check":
            print(
                "Error: --fix/--fix-all can only be used with --mode check.",
                file=sys.stderr,
            )
            sys.exit(1)
        exit_code = run_fix(
            project_root,
            min_score=args.min_score,
            fix_all=args.fix_all,
            run_tests=args.test,
            max_retries=args.max_retries,
            ollama_url=args.ollama_url,
            ollama_model=args.model,
            ignore_path_contains_all=ignore_path_contains_all,
        )
    elif args.mode == "check":
        exit_code = run_check(
            project_root, args.min_score, ignore_path_contains_all, args.show_excluded
        )
    else:
        exit_code = run_report(
            project_root, ignore_path_contains_all, args.show_excluded
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
