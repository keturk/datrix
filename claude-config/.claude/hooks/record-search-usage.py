"""PostToolUse hook: log code-search tool calls, and point the agent at the cheaper tool.

After a whole read of a large Python file, the agent is told the index call that answers it
(``additionalContext``): the MCP tool where the session has it, the shell command where it does
not. (A grep for a bare identifier is answered from the index before it runs, by
``redirect-identifier-grep.py``.) After a whole read of a large log, an
agent whose session has the local-model tools is pointed at ``digest_log``; after a whole
read of a large Python file, also at ``ask_files``. Each kind of hint is given up to three
times per agent context. See "Pointing the agent at the index" below for why.

Appends one JSON line per call to ``<workspace>/.code-index/usage.jsonl`` on this machine,
capped at ``SEARCH_USAGE_LOG_MAX_BYTES`` with one rotated file (``_hook_log.py``):
every code-index MCP tool call, and every call the index could have answered instead --
Grep, Glob, a Read of a Python file, and a shell command running a text search. Each line
records the tool, what was searched or read (a pattern or a path, never file content),
and the size of the answer, which is what the call cost in context. The report is
``code-index.ps1 -Usage``.

The workspace is derived from this file's REAL location
(``<workspace>/datrix/claude-config/.claude/hooks/``), so the log lands beside the index it
measures on whichever machine runs it, whether the hook is started through the workspace's
``.claude`` link or by its path inside the ``datrix`` repository -- never inside the repository.

Always exits 0 -- it observes, it never blocks, and a failure to log never disturbs the
tool call it observed.
"""

import json
import os
import re
import sys
from datetime import UTC, datetime
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_log import SEARCH_USAGE_LOG_MAX_BYTES, append_record  # noqa: E402
from _mcp_registration import (  # noqa: E402
    CODE_INDEX_SERVER,
    LOCAL_LLM_SERVER,
    is_registered,
    session_directory,
)
from _tool_names import READ_TOOLS  # noqa: E402

# <workspace>/datrix/claude-config/.claude/hooks/<this file>: five levels up from the real path.
_WORKSPACE: Final = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))))
# Must match code_index.sources.INDEX_DIR_NAME and USAGE_LOG_NAME, which the report reads.
_LOG_PATH: Final = os.path.join(_WORKSPACE, ".code-index", "usage.jsonl")

_INDEX_TOOL_PREFIX: Final = f"mcp__{CODE_INDEX_SERVER}__"
_SHELL_TOOLS: Final = frozenset({"Bash", "PowerShell"})
# A shell command that searches files: rg, grep, git grep, Select-String or findstr run as a
# command of its own (at the start, or after ; & && ( or a newline) ...
_SEARCH_TOOL: Final = r"(?:rg|grep|git\s+grep|select-string|sls|findstr)\b"
_DIRECT_SEARCH: Final = re.compile(rf"(?:^|[;&(\n])\s*(?:&\s*)?{_SEARCH_TOOL}", re.IGNORECASE)
# ... or fed a file listing through a pipe. A search piped from anything else filters a
# command's output (``pytest ... | Select-String FAILED``) and is not a code search.
_PIPED_SEARCH: Final = re.compile(rf"\|\s*{_SEARCH_TOOL}", re.IGNORECASE)
_FILE_LISTING: Final = re.compile(r"(?:^|[\s;&(|])(?:get-childitem|gci|dir|ls|find)\s", re.IGNORECASE)
_MAX_DETAIL_CHARS: Final = 300


def _is_code_search(command: str) -> bool:
    if _DIRECT_SEARCH.search(command):
        return True
    return bool(_PIPED_SEARCH.search(command) and _FILE_LISTING.search(command))


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
    if tool in READ_TOOLS:
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
    tool_name = str(data.get("tool_name", ""))
    raw_input = data.get("tool_input")
    tool_input = raw_input if isinstance(raw_input, dict) else {}
    response_chars = _response_chars(data.get("tool_response"))
    session = str(data.get("session_id", ""))
    agent = str(data.get("agent_id", "")) or "main"
    directory = session_directory(str(data.get("cwd", "")))
    entry = _entry(tool_name, tool_input)
    if entry is None:
        hint, kind = _log_read_hint(tool_name, tool_input, response_chars, directory), _LOG_READ_KIND
    else:
        entry.update(detail=str(entry["detail"])[:_MAX_DETAIL_CHARS], response_chars=response_chars,
                     session=session, agent=agent, ts=datetime.now(UTC).isoformat(timespec="seconds"))
        _append(entry)
        hint, kind = _hint(entry, directory), str(entry["category"])
    # Each subagent starts with a fresh context, so it gets its own share: keyed by session AND agent.
    if hint and _take_hint_slot(f"{session}-{agent}", kind):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": hint}}))
    sys.exit(0)


def _append(entry: dict[str, object]) -> None:
    # Reported, not raised: a lost log line must never disturb the tool call it observed.
    append_record(_LOG_PATH, entry, "record-search-usage", SEARCH_USAGE_LOG_MAX_BYTES)


# --- Pointing the agent at the index ----------------------------------------------------
# Measured on the first full day: subagents ran 1,293 greps, 294 of them a bare identifier,
# and called the index 11 times. The index tools are deferred (they need a ToolSearch before
# first use) and nothing on an agent's path names them, so a lookup the index answers in one
# call went to grep-and-read instead. Right after such a call the agent is told the exact
# call that answers it -- once per kind per agent, then silence: a hint repeated is paid for
# again on every later turn, and an agent that ignored it once ignores it the second time too.
#
# The call named depends on what the session has. The MCP tools exist only where
# ``code-index.ps1 -Setup`` registered the server for the session's directory; a hint naming
# them anywhere else sends the agent to a ToolSearch that finds nothing, and it goes back to
# grep. So an unregistered session is given the shell command, and told why its tools are
# missing.

_HINTS_PER_SESSION_PER_KIND: Final = 1
_HINT_STATE_DIR: Final = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")
_LOCAL_PREFIX: Final = f"mcp__{LOCAL_LLM_SERVER}__"
_LARGE_READ_CHARS: Final = 8000
_LOG_READ_KIND: Final = "log_read"
_LOG_SUFFIXES: Final = (".log",)
# Where test, generation and deploy runs write their output: anything read whole from here is a log.
_LOG_DIRS: Final = (".test-output", ".test_results")
_CODE_INDEX_SCRIPT: Final = os.path.join(_WORKSPACE, "datrix", "scripts", "dev", "code-index.ps1").replace("\\", "/")


def _unregistered_note(cwd: str) -> str:
    return f"(Index MCP tools absent here: tell Jon once to run `{_CODE_INDEX_SCRIPT} -Setup` and reload.)"


def _large_read_hint(response_chars: int, cwd: str) -> str:
    cost = f"Code index: that read cost ~{response_chars // 4:,} tokens; "
    if is_registered(cwd, CODE_INDEX_SERVER):
        hint = (
            f"{cost}{_INDEX_TOOL_PREFIX}outline gives line ranges to read by offset/limit "
            f"(ToolSearch 'select:{_INDEX_TOOL_PREFIX}outline')."
        )
    else:
        hint = (
            f"{cost}`powershell -File \"{_CODE_INDEX_SCRIPT}\" -Outline <path>` gives line ranges to read by "
            f"offset/limit. {_unregistered_note(cwd)}"
        )
    if is_registered(cwd, LOCAL_LLM_SERVER):
        hint += f" {_LOCAL_PREFIX}ask_files answers questions about a file without reading it."
    return hint


def _is_log(path: str) -> bool:
    normalised = path.replace("\\", "/").lower()
    return normalised.endswith(_LOG_SUFFIXES) or any(f"/{name}/" in normalised for name in _LOG_DIRS)


def _log_read_hint(tool: str, tool_input: dict[str, object], response_chars: int, cwd: str) -> str:
    """After a whole read of a large log, point a session that has the local-model tools at digest_log."""
    if tool not in READ_TOOLS or "offset" in tool_input or "limit" in tool_input:
        return ""
    if response_chars < _LARGE_READ_CHARS or not _is_log(str(tool_input.get("file_path", ""))):
        return ""
    if not is_registered(cwd, LOCAL_LLM_SERVER):
        return ""
    return (
        f"Local models: that log read cost ~{response_chars // 4:,} tokens; {_LOCAL_PREFIX}digest_log lists a "
        f"log's distinct failures without reading it (ToolSearch 'select:{_LOCAL_PREFIX}digest_log')."
    )


def _hint(entry: dict[str, object], cwd: str) -> str:
    category = entry.get("category")
    response_chars = int(str(entry.get("response_chars", 0)))
    if category == "read" and not entry.get("ranged") and response_chars >= _LARGE_READ_CHARS:
        return _large_read_hint(response_chars, cwd)
    return ""


def _take_hint_slot(context: str, kind: str) -> bool:
    """Count one hint of ``kind`` for one agent's context; False once it has had its share."""
    safe = "".join(c for c in context if c.isalnum() or c in "-_")[:96] or "unknown"
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
