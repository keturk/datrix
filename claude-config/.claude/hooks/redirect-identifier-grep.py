"""PreToolUse(Grep) hook: the first grep for a bare identifier gets the code index's answer instead.

Agents look up a definition or its uses with a text search: in the usage log, 294 of 1,293
subagent greps on the first measured day were one bare identifier, and the index -- which
answers that lookup exactly, in one call -- was called 11 times. A hint after the grep did not
change that: the agent had its grep output already.

So the harness answers it. The FIRST grep, by one agent, whose pattern is one identifier
(optionally dotted, a ``def``/``class`` prefix, word boundaries or a trailing call paren --
``datrix_scripts.code_index.usage.IDENTIFIER_GREP_PATTERN``, the definition the usage report
counts by), fenced to nothing but Python or to nothing at all, over a framework repository or the
workspace, is refused (exit 2) with:

  * the definitions ``find_symbol`` holds for the name, and
  * for a bare name (not ``def X``/``class X``, which asks for the definition only) the uses
    ``find_references`` holds -- resolved through imports when the name has one definition.

The index is refreshed first, so the answer is the code as it is now. If the agent needs the
text search after all -- a string, a comment, a file the index does not cover -- it repeats the
grep, and the repeat goes through: the notice is shown once per name per agent
(``.state/grep-redirect-<session>-<agent>.json``).

It never refuses a case-insensitive or multiline search, a grep fenced to another language, a
search outside the framework repositories, a name the index holds no definition of, or anything
when something goes wrong: every failure here exits 0 and the grep proceeds. Each redirect is a
``grep_redirect`` line in the code-index usage log, and each repeat that went through a
``grep_redirect_repeat`` line, so ``code-index.ps1 -Usage`` shows how often the answer sufficed.
"""

import json
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_log import WORKSPACE, add_scripts_lib_to_path, append_record  # noqa: E402
from _mcp_registration import CODE_INDEX_SERVER, is_registered, session_directory  # noqa: E402

# Must match datrix_scripts.code_index.usage.CATEGORY_GREP_REDIRECT / CATEGORY_GREP_REDIRECT_REPEAT, which the report reads.
REDIRECT_CATEGORY: Final = "grep_redirect"
REPEAT_CATEGORY: Final = "grep_redirect_repeat"
MAX_DEFINITIONS: Final = 12
MAX_REFERENCE_FILES: Final = 25
MAX_ANSWER_CHARS: Final = 6_000
_STATE_DIR: Final = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")
_USAGE_LOG: Final = os.path.join(WORKSPACE, ".code-index", "usage.jsonl")
_USAGE_LOG_MAX_BYTES: Final = 8 * 1024 * 1024
_CODE_INDEX_SCRIPT: Final = os.path.join(WORKSPACE, "datrix", "scripts", "dev", "code-index.ps1").replace("\\", "/")
_INDEX_TOOL_PREFIX: Final = f"mcp__{CODE_INDEX_SERVER}__"
_DEFINITION_PREFIX: Final = re.compile(r"^(?:def|class)\s+")
_PYTHON_TYPE: Final = "py"
_PYTHON_SUFFIX: Final = ".py"


def _python_scoped(tool_input: dict[str, object]) -> bool:
    """False when the grep is fenced to something other than Python."""
    kind, glob, path = (str(tool_input.get(key, "")) for key in ("type", "glob", "path"))
    if kind and kind != _PYTHON_TYPE:
        return False
    if glob and _PYTHON_SUFFIX not in glob:
        return False
    extension = os.path.splitext(path)[1].lower()
    return not extension or extension == _PYTHON_SUFFIX


def bare_name(pattern: str) -> str:
    """The identifier a pattern IDENTIFIER_GREP_PATTERN accepted names: prefix, boundaries and paren stripped."""
    name = re.sub(r"^(?:def\s+|class\s+)|\\b|\\?\($", "", pattern)
    return name.replace("\\.", ".")


def _search_root(tool_input: dict[str, object], cwd: str) -> Path | None:
    raw = str(tool_input.get("path", "")) or cwd
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        if not cwd:
            return None
        path = Path(cwd) / path
    return path.resolve()


def _indexed_root(root: Path, workspace: Path) -> bool:
    """The workspace itself, or a path inside one of its framework repositories (what the index covers)."""
    from datrix_scripts.framework_repos import framework_repos

    resolved = workspace.resolve()
    return root == resolved or any(root.is_relative_to(repo.resolve()) for repo in framework_repos(resolved))


def _state_path(session: str, agent: str) -> str:
    safe = "".join(c for c in f"{session}-{agent}" if c.isalnum() or c in "-_")[:96] or "unknown"
    return os.path.join(_STATE_DIR, f"grep-redirect-{safe}.json")


def _told(state: str) -> list[str]:
    try:
        with open(state, encoding="utf-8") as handle:
            told = json.load(handle)
    except (OSError, ValueError):
        return []
    return [str(entry) for entry in told] if isinstance(told, list) else []


def _mark_told(state: str, name: str) -> None:
    """Record that the agent was answered for ``name``: its repeat grep is let through."""
    told = [*_told(state), name]  # read before the file is opened for writing, which empties it
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(state, "w", encoding="utf-8") as handle:
            json.dump(told, handle)
    except OSError as exc:
        sys.stderr.write(f"redirect-identifier-grep: could not record the notice in {state}: {exc}\n")


def _clip(text: str) -> str:
    if len(text) <= MAX_ANSWER_CHARS:
        return text
    kept = text[:MAX_ANSWER_CHARS].rsplit("\n", 1)[0]
    return f"{kept}\n... clipped: ask the index tool for the rest."


def _index_answer(workspace: Path, name: str, definitions_only: bool) -> str:
    """Definitions (and, for a bare name, uses) from the refreshed index; empty when it holds no definition."""
    from datrix_scripts.code_index.queries import QueryError, find_references, find_symbol
    from datrix_scripts.code_index.session import open_session
    from datrix_scripts.code_index.sources import CodeIndexError

    try:
        session = open_session(workspace)
    except CodeIndexError:
        return ""
    try:
        session.refresh()
        symbols = find_symbol(session.conn, name, limit=MAX_DEFINITIONS)
        if not symbols.hits:
            return ""
        answer = f"Definitions:\n{symbols.render()}"
        if not definitions_only:
            references = find_references(session.conn, name, file_limit=MAX_REFERENCE_FILES)
            answer += f"\n\nUses:\n{references.render()}"
    except (QueryError, CodeIndexError):
        return ""
    finally:
        session.close()
    return _clip(answer)


def _tool_note(name: str, directory: str) -> str:
    if is_registered(directory, CODE_INDEX_SERVER):
        return (f"Next time ask the index directly: {_INDEX_TOOL_PREFIX}find_symbol / find_references "
                f"(ToolSearch 'select:{_INDEX_TOOL_PREFIX}find_symbol,{_INDEX_TOOL_PREFIX}find_references').")
    return (f"Next time ask the index directly: `powershell -File \"{_CODE_INDEX_SCRIPT}\" -Symbol {name}` or "
            f"`-References <dotted.path>`.")


def _message(name: str, answer: str, directory: str) -> str:
    return (
        f"GREP REDIRECTED: the code index answers '{name}' exactly (refreshed just now):\n\n{answer}\n\n"
        f"{_tool_note(name, directory)}\n"
        f"If you need the text search itself (a string, a comment, a file the index does not cover), repeat the "
        f"same Grep: this notice is shown once per name per agent."
    )


def decide(payload: dict[str, object], workspace: Path, on_repeat: Callable[[], None] | None = None) -> str:
    """The refusal message for this Grep, or the empty string to let it through.

    ``on_repeat`` is called when the grep repeats one already answered: the agent ran the text
    search after all."""
    tool_input = payload.get("tool_input")
    if payload.get("tool_name") != "Grep" or not isinstance(tool_input, dict):
        return ""
    if tool_input.get("-i") or tool_input.get("multiline") or not _python_scoped(tool_input):
        return ""
    add_scripts_lib_to_path()
    from datrix_scripts.code_index.usage import IDENTIFIER_GREP_PATTERN

    pattern = str(tool_input.get("pattern", ""))
    if not IDENTIFIER_GREP_PATTERN.match(pattern):
        return ""
    cwd = str(payload.get("cwd", ""))
    root = _search_root(tool_input, cwd)
    if root is None or not _indexed_root(root, workspace):
        return ""
    name = bare_name(pattern)
    state = _state_path(str(payload.get("session_id", "")), str(payload.get("agent_id", "")) or "main")
    if name in _told(state):
        if on_repeat is not None:
            on_repeat()
        return ""
    answer = _index_answer(workspace, name, definitions_only=bool(_DEFINITION_PREFIX.match(pattern)))
    if not answer:
        return ""
    _mark_told(state, name)
    return _message(name, answer, session_directory(cwd))


def _record(payload: dict[str, object], category: str, response_chars: int) -> None:
    tool_input = payload.get("tool_input")
    detail = str(tool_input.get("pattern", "")) if isinstance(tool_input, dict) else ""
    append_record(_USAGE_LOG, {
        "category": category, "tool": "Grep", "detail": detail[:300], "response_chars": response_chars,
        "session": str(payload.get("session_id", "")), "agent": str(payload.get("agent_id", "")) or "main",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }, "redirect-identifier-grep", _USAGE_LOG_MAX_BYTES)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    try:
        add_scripts_lib_to_path()
        from datrix_scripts.paths import WORKSPACE_DIR

        message = decide(payload, WORKSPACE_DIR, on_repeat=lambda: _record(payload, REPEAT_CATEGORY, 0))
    except Exception as exc:  # a hook must never fail the tool call it observed
        sys.stderr.write(f"redirect-identifier-grep: skipped: {type(exc).__name__}: {exc}\n")
        sys.exit(0)
    if not message:
        sys.exit(0)
    _record(payload, REDIRECT_CATEGORY, len(message))
    sys.stderr.write(message + "\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
