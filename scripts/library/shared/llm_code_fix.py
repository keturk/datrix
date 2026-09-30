"""Shared machinery for scripts that ask a local model to rewrite Python code.

Used by: metrics/complexity.py, metrics/error_messages.py, metrics/test_gen.py

Provides parsing of a model's code answer, file context for prompts, verification of a
rewrite on disk (ruff + pytest, reverting on failure), and indentation handling. Talking
to the model servers themselves is ``shared.local_llm``.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_FIX_RETRIES = 3

PYTEST_TIMEOUT_SECONDS = 600
RUFF_TIMEOUT_SECONDS = 30
# Ruff's stderr warning for a file it could not read; it still exits 0 after it.
RUFF_UNREAD_FILE_MARKER = "Failed to lint"

# Verification outcomes callers branch on.
FILE_MODIFIED = "file_modified"
TEST_FAILURE = "test_failure"

_CONTEXT_MAX_IMPORT_LINES = 80
_CONTEXT_MAX_INIT_LINES = 15
_CONTEXT_MAX_CONSTANT_LINES = 20
_CONTEXT_MAX_METHODS = 30

_CODE_FENCE_PATTERN = re.compile(r"```(?:python)?\s*\n(.*?)```", flags=re.DOTALL)


def parse_code_response(response: str) -> str | None:
    """Extract Python code from a model answer (reasoning already stripped).

    Takes the first fenced block, or the whole answer when there is no fence. Returns
    None when nothing is left -- a failed attempt the caller retries with feedback.
    """
    code_match = _CODE_FENCE_PATTERN.search(response)
    code = code_match.group(1).strip() if code_match else response.strip()
    if not code:
        return None
    # Normalize to LF -- a model may answer with CRLF depending on its training data.
    return code.replace("\r\n", "\n")


# --- Context extraction ---


def extract_file_context(
    source: str,
    func_name: str,
    func_lineno: int,
) -> str:
    """Extract relevant file context for LLM prompts.

    Includes: imports, class signature, __init__ attributes, sibling method signatures,
    module-level constants.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    lines = source.splitlines()
    sections: list[str] = []
    sections.append(
        "# File context (for reference only — do not reproduce in your output):"
    )
    imports = extract_imports(tree, lines)
    if imports:
        sections.append(f"## Imports\n```python\n{imports}\n```")
    class_ctx = extract_class_context(tree, lines, func_name, func_lineno)
    if class_ctx:
        sections.append(class_ctx)
    constants = extract_module_constants(tree, lines, _CONTEXT_MAX_CONSTANT_LINES)
    if constants:
        sections.append(f"## Module constants\n```python\n{constants}\n```")
    return "\n\n".join(sections)


def extract_imports(tree: ast.Module, lines: list[str]) -> str:
    """Extract import statements from file (capped at max_lines)."""
    import_lines: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        start = node.lineno - 1
        end = node.end_lineno if node.end_lineno is not None else node.lineno
        for i in range(start, min(end, len(lines))):
            import_lines.append(lines[i].rstrip())
        if len(import_lines) >= _CONTEXT_MAX_IMPORT_LINES:
            break
    return "\n".join(import_lines[:_CONTEXT_MAX_IMPORT_LINES])


def extract_class_context(
    tree: ast.Module,
    lines: list[str],
    func_name: str,
    func_lineno: int,
) -> str | None:
    """Extract class header + __init__ + method signatures for enclosing class."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        method_match = any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == func_name
            and item.lineno == func_lineno
            for item in node.body
        )
        if not method_match:
            continue
        header_line = lines[node.lineno - 1].rstrip()
        parts: list[str] = [f"## Class context\n{header_line}"]
        init_lines = _extract_init_lines(node, lines)
        if init_lines:
            parts.append(f"### __init__ attributes\n{init_lines}")
        sigs = _extract_method_signatures(node, lines, func_name, func_lineno)
        if sigs:
            parts.append(f"### Other methods in the class\n{sigs}")
        return "\n\n".join(parts)
    return None


def _extract_init_lines(class_node: ast.ClassDef, lines: list[str]) -> str:
    """Extract __init__ method signature and self.x assignments."""
    for item in class_node.body:
        if not isinstance(item, ast.FunctionDef) or item.name != "__init__":
            continue
        result: list[str] = [lines[item.lineno - 1].rstrip()]
        count = 1
        for stmt in ast.walk(item):
            if count >= _CONTEXT_MAX_INIT_LINES:
                break
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if isinstance(target, ast.Attribute) and isinstance(
                    target.value, ast.Name
                ) and target.value.id == "self":
                    line_idx = stmt.lineno - 1
                    if 0 <= line_idx < len(lines):
                        result.append(lines[line_idx].rstrip())
                        count += 1
                    break
        return "\n".join(result)
    return ""


def _extract_method_signatures(
    class_node: ast.ClassDef,
    lines: list[str],
    skip_name: str,
    skip_lineno: int,
) -> str:
    """Extract method signatures (def line only) for sibling methods."""
    sigs: list[str] = []
    for item in class_node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if item.name == skip_name and item.lineno == skip_lineno:
            continue
        if len(sigs) >= _CONTEXT_MAX_METHODS:
            break
        sig_line = lines[item.lineno - 1].rstrip()
        if item.decorator_list:
            dec_line = lines[item.decorator_list[0].lineno - 1].rstrip()
            sigs.append(dec_line)
        sigs.append(f"{sig_line} ...")
    return "\n".join(sigs)


def extract_module_constants(
    tree: ast.Module,
    lines: list[str],
    max_lines: int = _CONTEXT_MAX_CONSTANT_LINES,
) -> str:
    """Extract top-level assignment statements (constants/config)."""
    result: list[str] = []
    for node in tree.body:
        if len(result) >= max_lines:
            break
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            start = node.lineno - 1
            end = node.end_lineno if node.end_lineno is not None else node.lineno
            for i in range(start, min(end, len(lines))):
                result.append(lines[i].rstrip())
                if len(result) >= max_lines:
                    break
    return "\n".join(result)


# --- Fix validation ---


def apply_and_verify_on_disk(
    file_path: Path,
    original_content: str,
    fixed_content: str,
    original_hash: str,
    project_root: Path,
    run_tests: bool = False,
) -> tuple[bool, str]:
    """Write fixed content to disk, run ruff check, optionally run pytest.

    Reverts to original content on failure.
    Returns (success, error_message); error_message is FILE_MODIFIED when the file
    changed under the run, TEST_FAILURE when the tests failed, else the ruff output.
    """
    current_content = file_path.read_text(encoding="utf-8")
    current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
    if current_hash != original_hash:
        logger.warning("file_modified_during_processing file=%s", file_path)
        return False, FILE_MODIFIED

    file_path.write_text(fixed_content, encoding="utf-8", newline="\n")

    ruff_ok, ruff_details = run_ruff_check(file_path)
    if not ruff_ok:
        logger.info("reverting_due_to_ruff_errors file=%s", file_path)
        file_path.write_text(original_content, encoding="utf-8", newline="\n")
        return False, ruff_details

    if run_tests:
        test_ok, _ = run_pytest(project_root)
        if not test_ok:
            logger.info("reverting_due_to_test_failures file=%s", file_path)
            file_path.write_text(original_content, encoding="utf-8", newline="\n")
            return False, TEST_FAILURE

    return True, ""


def run_ruff_check(file_path: Path) -> tuple[bool, str]:
    """Run ruff check --select F821 (undefined names). Returns (passed, output).

    A check that cannot run is a failed check: a rewrite is kept only when ruff
    actually passed it. Ruff reports a file it could not read as a warning and still
    exits 0 ("All checks passed!"), so that warning is a failure here.
    """
    if not file_path.is_file():
        return False, f"ruff check cannot run: {file_path} is not a file"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--select", "F821", str(file_path)],
            capture_output=True,
            text=True,
            timeout=RUFF_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"ruff check timed out after {RUFF_TIMEOUT_SECONDS}s on {file_path}"
    if RUFF_UNREAD_FILE_MARKER in result.stderr:
        return False, result.stderr.strip()
    if result.returncode != 0:
        details = (result.stdout or result.stderr).strip()
        return False, details or f"ruff check exited {result.returncode} on {file_path}"
    return True, ""


def run_pytest(project_root: Path) -> tuple[bool, str]:
    """Run pytest with fail-fast, no coverage. Returns (passed, output).

    A test run that cannot start or finish is a failed run: a rewrite is kept only
    when the tests actually passed.
    """
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=short",
                "--no-cov", "--override-ini=addopts=",
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"Tests timed out after {PYTEST_TIMEOUT_SECONDS}s"
    if result.returncode != 0:
        output = (result.stdout or result.stderr).strip()
        return False, output
    return True, ""


# --- Indentation ---


def detect_indent(source: str) -> str:
    """Detect the base indentation of a code block (first non-empty line)."""
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped:
            return line[: len(line) - len(stripped)]
    return ""


def normalize_indentation(code: str, target_indent: str) -> str:
    """Re-indent code block to match target indentation."""
    lines = code.splitlines(keepends=True)
    if not lines:
        return code
    # Detect current base indentation from first non-empty line
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
    return "".join(result)


# --- Retry ---


def build_retry_feedback(error: str, attempt: int, max_retries: int) -> str:
    """Build feedback message for retry attempt."""
    return (
        f"Your previous attempt (attempt {attempt}/{max_retries}) failed:\n"
        f"{error}\n\n"
        "Please fix the issue and try again with a different approach."
    )
