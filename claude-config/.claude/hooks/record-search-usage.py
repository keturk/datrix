"""PostToolUse hook: log code-search tool calls, so code-index adoption can be measured.

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
    sys.exit(0)


if __name__ == "__main__":
    main()
