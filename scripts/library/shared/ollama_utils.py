"""Shared Ollama utilities for LLM-assisted code quality tools.

Used by: metrics/complexity.py, metrics/error_messages.py

Provides common infrastructure for calling a local Ollama server, parsing
LLM responses, extracting file context for prompts, validating fixes on disk
(ruff + pytest), and managing indentation.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Configuration ---
OLLAMA_DEFAULT_URL = "http://10.94.0.100:11434"
OLLAMA_DEFAULT_MODEL = "qwen3-coder-cline:latest"
OLLAMA_TIMEOUT_SECONDS = 300
OLLAMA_DEFAULT_NUM_PREDICT = 32768
OLLAMA_MAX_FIX_RETRIES = 3

PYTEST_TIMEOUT_SECONDS = 600

_CONTEXT_MAX_IMPORT_LINES = 80
_CONTEXT_MAX_INIT_LINES = 15
_CONTEXT_MAX_CONSTANT_LINES = 20
_CONTEXT_MAX_METHODS = 30


# --- Ollama API ---


def call_ollama(
    system_prompt: str,
    user_prompt: str,
    ollama_url: str = OLLAMA_DEFAULT_URL,
    ollama_model: str = OLLAMA_DEFAULT_MODEL,
    timeout: int = OLLAMA_TIMEOUT_SECONDS,
    num_predict: int = OLLAMA_DEFAULT_NUM_PREDICT,
    temperature: float = 0.3,
    keep_alive: str | None = None,
) -> str | None:
    """POST to Ollama /api/chat endpoint. Returns response text or None on error."""
    body = {
        "model": ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    if keep_alive:
        body["keep_alive"] = keep_alive
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        logger.error("ollama_connection_failed url=%s error=%s", ollama_url, e)
        return None
    except TimeoutError:
        logger.error("ollama_timeout seconds=%d", timeout)
        return None

    content: str = data["message"]["content"]
    return content


def parse_ollama_response(response: str) -> str | None:
    """Extract Python code from Ollama response.

    Strips <think> tags, markdown code fences, and leading/trailing whitespace.
    Returns None if no valid code found.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
    code_match = re.search(r"```(?:python)?\s*\n(.*?)```", cleaned, flags=re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()
    else:
        code = cleaned.strip()

    if not code:
        return None

    # Normalize to LF — Ollama may return CRLF depending on model training data.
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
    Returns (success, error_message).
    """
    import hashlib

    current_content = file_path.read_text(encoding="utf-8")
    current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
    if current_hash != original_hash:
        logger.warning("file_modified_during_processing file=%s", file_path)
        return False, "file_modified"

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
            return False, "test_failure"

    return True, ""


def run_ruff_check(file_path: Path) -> tuple[bool, str]:
    """Run ruff check --select F821 (undefined names). Returns (passed, output)."""
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "F821", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return True, ""
    except subprocess.TimeoutExpired:
        return True, ""
    if result.returncode != 0:
        details = result.stdout.strip()
        return False, details
    return True, ""


def run_pytest(project_root: Path) -> tuple[bool, str]:
    """Run pytest with fail-fast, no coverage. Returns (passed, output)."""
    try:
        result = subprocess.run(
            [
                "python", "-m", "pytest", "tests/", "-x", "-q", "--tb=short",
                "--no-cov", "--override-ini=addopts=",
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"Tests timed out after {PYTEST_TIMEOUT_SECONDS}s"
    if result.returncode != 0:
        output = result.stdout.strip()
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
