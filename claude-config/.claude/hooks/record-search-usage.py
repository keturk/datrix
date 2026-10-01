"""PostToolUse hook: log code-search tool calls, and point the agent at the code index.

After a grep for a bare identifier in Python, or a whole read of a large Python file, the
agent is told the index call that answers it (``additionalContext``), up to three times per
session per kind. See "Pointing the agent at the index" below for why.

Appends one JSON line per call to ``<workspace>/.code-index/usage.jsonl`` on this machine:
every code-index MCP tool call, and every call the index could have answered instead --
Grep, Glob, a Read of a Python file, and a shell command running a text search. Each line
records the tool, what was searched or read (a pattern or a path, never file content),
and the size of the answer, which is what the call cost in context. The report is
``code-index.ps1 -Usage``.

The workspace is derived from this file's own location (``<workspace>/.claude/hooks/``),
so the log lands beside the index it measures on whichever machine runs it.

Always exits 0 -- it observes, it never blocks, and a failure to log never disturbs the
tool call it observed.
"""

import json
import os
import re
import sys
from datetime import UTC, datetime
from typing import Final

_WORKSPACE: Final = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Must match code_index.sources.INDEX_DIR_NAME and USAGE_LOG_NAME, which the report reads.
_LOG_PATH: Final = os.path.join(_WORKSPACE, ".code-index", "usage.jsonl")

_INDEX_TOOL_PREFIX: Final = "mcp__datrix-code-index__"
_SHELL_TOOLS: Final = frozenset({"Bash", "PowerShell"})
# A shell command that searches files: rg, grep, git grep, Select-String or findstr run as a
# command of its own (at the start, or after ; & && ( or a newline) ...
_SEARCH_TOOL: Final = r"(?:rg|grep|git\s+grep|select-string|sls|findstr)\b"
_DIRECT_SEARCH: Final = re.compile(rf"(?:^|[;&(\n])\s*(?:&\s*)?{_SEARCH_TOOL}", re.IGNORECASE)
# ... or fed a file listing through a pipe. A search piped from anything else filters a
# command's output (``pytest ... | Select-String FAILED``) and is not a code search.
_PIPED_SEARCH: Final = re.compile(rf"\|\s*{_SEARCH_TOOL}", re.IGNORECASE)
_FILE_LISTING: Final = re.compile(r"(?:^|[\s;&(|])(?:get-childitem|gci|dir|ls|find)\s", re.IGNORECASE)


def _is_code_search(command: str) -> bool:
    if _DIRECT_SEARCH.search(command):
        return True
    return bool(_PIPED_SEARCH.search(command) and _FILE_LISTING.search(command))
_MAX_DETAIL_CHARS: Final = 300


def _response_chars(response: object) -> int:
    if isinstance(response, str):
        return len(response)
    try:
        return len(json.dumps(response, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0


def _entry(tool: str, tool_input: dict[str, object]) -> dict[str, object] | None:
    """What to record about one call, or None when the call is not a code search."""
    if tool.startswith(_INDEX_TOOL_PREFIX):
        return {"category": "index", "tool": tool[len(_INDEX_TOOL_PREFIX):],
                "detail": json.dumps(tool_input, ensure_ascii=False)}
    if tool == "Grep":
        return {"category": "grep", "tool": tool, "detail": str(tool_input.get("pattern", "")),
                "path": str(tool_input.get("path", "")), "glob": str(tool_input.get("glob", "")),
                "type": str(tool_input.get("type", ""))}
    if tool == "Glob":
        return {"category": "glob", "tool": tool, "detail": str(tool_input.get("pattern", ""))}
    if tool == "Read":
        path = str(tool_input.get("file_path", ""))
        if not path.lower().endswith(".py"):
            return None
        ranged = "offset" in tool_input or "limit" in tool_input
        return {"category": "read", "tool": tool, "detail": path, "ranged": ranged}
    if tool in _SHELL_TOOLS:
        command = str(tool_input.get("command", ""))
        if not _is_code_search(command):
            return None
        return {"category": "shell_search", "tool": tool, "detail": command}
    return None


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)
    tool_input = data.get("tool_input")
    entry = _entry(str(data.get("tool_name", "")), tool_input if isinstance(tool_input, dict) else {})
    if entry is None:
        sys.exit(0)
    entry["detail"] = str(entry["detail"])[:_MAX_DETAIL_CHARS]
    entry["response_chars"] = _response_chars(data.get("tool_response"))
    entry["session"] = str(data.get("session_id", ""))
    entry["agent"] = str(data.get("agent_id", "")) or "main"
    entry["ts"] = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        # Reported, not raised: a lost log line must never disturb the tool call it observed.
        sys.stderr.write(f"record-search-usage: could not append to {_LOG_PATH}: {exc}\n")
    hint = _hint(entry)
    if hint and _take_hint_slot(entry["session"], str(entry["category"])):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": hint}}))
    sys.exit(0)


# --- Pointing the agent at the index ----------------------------------------------------
# Measured on the first full day: subagents ran 1,293 greps, 294 of them a bare identifier,
# and called the index 11 times. The index tools are deferred (they need a ToolSearch before
# first use) and nothing on an agent's path names them, so a lookup the index answers in one
# call went to grep-and-read instead. Right after such a call the agent is told the exact
# call that answers it -- a few times per session, then silence.

_HINTS_PER_SESSION_PER_KIND: Final = 3
_HINT_STATE_DIR: Final = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")
_TOOL_PREFIX: Final = "mcp__datrix-code-index__"
_LARGE_READ_CHARS: Final = 8000


def _identifier_pattern() -> re.Pattern[str] | None:
    """The usage report's definition of an identifier grep, so hint and report agree."""
    library = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))), "scripts", "library")
    if library not in sys.path:
        sys.path.insert(0, library)
    try:
        from code_index.usage import IDENTIFIER_GREP_PATTERN
    except ImportError:
        return None
    return IDENTIFIER_GREP_PATTERN


def _python_scoped(entry: dict[str, object]) -> bool:
    """False when the grep is fenced to something other than Python, which the index does not cover."""
    kind, glob, path = str(entry.get("type", "")), str(entry.get("glob", "")), str(entry.get("path", ""))
    if kind and kind != "py":
        return False
    if glob and ".py" not in glob:
        return False
    extension = os.path.splitext(path)[1].lower()
    return not extension or extension == ".py"


def _bare_name(pattern: str) -> str:
    name = re.sub(r"^(?:def\s+|class\s+)|\\b|\\?\($", "", pattern)
    return name.replace("\\.", ".")


def _hint(entry: dict[str, object]) -> str:
    category, detail = entry.get("category"), str(entry.get("detail", ""))
    if category == "grep" and _python_scoped(entry):
        pattern = _identifier_pattern()
        if pattern is None or not pattern.match(detail):
            return ""
        name = _bare_name(detail)
        return (
            f"Code index: '{name}' is a definition or usage lookup. {_TOOL_PREFIX}find_symbol (where it is "
            f"defined) and {_TOOL_PREFIX}find_references (every use, resolved through imports) answer it across "
            f"every repo in one call. Load them first with ToolSearch query "
            f"'select:{_TOOL_PREFIX}find_symbol,{_TOOL_PREFIX}find_references'. Grep stays right for strings, "
            f"comments, templates and non-Python files."
        )
    if category == "read" and not entry.get("ranged") and int(str(entry.get("response_chars", 0))) >= _LARGE_READ_CHARS:
        return (
            f"Code index: that whole-file read cost about {int(str(entry['response_chars'])) // 4:,} tokens. "
            f"{_TOOL_PREFIX}outline lists a file's definitions with line ranges; then Read only the lines you "
            f"need with offset/limit. Load it with ToolSearch query 'select:{_TOOL_PREFIX}outline'."
        )
    return ""


def _take_hint_slot(session: str, kind: str) -> bool:
    """Count one hint of ``kind`` for ``session``; False once the session has had its share."""
    safe = "".join(c for c in session if c.isalnum() or c in "-_")[:64] or "unknown"
    path = os.path.join(_HINT_STATE_DIR, f"search-hints-{safe}.json")
    try:
        with open(path, encoding="utf-8") as handle:
            counts = json.load(handle)
    except (OSError, ValueError):
        counts = {}
    if not isinstance(counts, dict):
        counts = {}
    used = counts[kind] if isinstance(counts.get(kind), int) else 0
    if used >= _HINTS_PER_SESSION_PER_KIND:
        return False
    counts[kind] = used + 1
    try:
        os.makedirs(_HINT_STATE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(counts, handle)
    except OSError as exc:
        sys.stderr.write(f"record-search-usage: could not record a hint in {path}: {exc}\n")
    return True


if __name__ == "__main__":
    main()
