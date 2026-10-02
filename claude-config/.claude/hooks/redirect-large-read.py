"""PreToolUse(Read) hook: the first whole read of a large file gets its outline, or a log its digest.

Agents read large Python files whole to answer a narrow question: over ten days of logged
reads, 26% of whole reads were of files over 16,000 characters, and those were 58% of every
token spent on whole reads. The code index's ``outline`` and the local models' ``digest_log``
answer most of those questions for a fraction of the cost, and agents did not reach for them,
with a hint or without one.

So the harness does it. The FIRST whole read, by one agent, of one large file in the
framework repositories is refused (exit 2) with what the agent wanted:

  * a ``.py`` file -- its outline: every definition with its line range and signature, and the
    module summary a local model wrote (``code_index.queries.outline``, refreshed first so the
    line ranges are the file's as it is now);
  * a ``.log`` file in test output -- the local model's digest of its distinct failures
    (``_local_digest``), which takes up to a minute.

The agent then reads the ranges it needs. If it does need the whole file -- to rewrite it, say
-- it repeats the same Read, and the repeat goes through: the notice is shown once per file per
agent (``.state/read-redirect-<session>-<agent>.json``). That is what keeps this from wedging
anyone, and what keeps every refusal a deliberate one.

It never refuses a ranged read (``offset``/``limit``), a file outside the framework
repositories, a small file, a file the index cannot outline, or anything when something goes
wrong: every failure here exits 0 and the read proceeds. Each redirect is a ``read_redirect``
line in the code-index usage log, and each repeat that went through a ``read_redirect_repeat``
line, so ``code-index.ps1 -Usage`` shows how many agents read ranges and how many read the
whole file anyway.
"""

import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_log import LIBRARY_DIR, WORKSPACE, append_record  # noqa: E402
from _local_digest import default_settings, digest_of  # noqa: E402
from _mcp_registration import (  # noqa: E402
    CODE_INDEX_SERVER,
    LOCAL_LLM_SERVER,
    is_registered,
    session_directory,
)

if TYPE_CHECKING:
    from shared.local_llm import LocalLlmSettings

CALLER: Final = "hook:large-read-digest"
# Must match code_index.usage.CATEGORY_READ_REDIRECT / CATEGORY_READ_REDIRECT_REPEAT, which the report reads.
REDIRECT_CATEGORY: Final = "read_redirect"
REPEAT_CATEGORY: Final = "read_redirect_repeat"
# On-disk size at which a whole read is redirected. A read adds a line number to every line,
# so 14,000 bytes is about the 16,000 characters the measurement above is made at.
LARGE_PY_BYTES: Final = 14_000
LARGE_LOG_BYTES: Final = 20_000
CHARS_PER_TOKEN: Final = 4
MAX_OUTLINE_LINES: Final = 140
MAX_OUTLINE_CHARS: Final = 7_000
_STATE_DIR: Final = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")
_USAGE_LOG: Final = os.path.join(WORKSPACE, ".code-index", "usage.jsonl")
_USAGE_LOG_MAX_BYTES: Final = 8 * 1024 * 1024
_LOG_DIRS: Final = (".test-output", ".test_results")


def _is_log(path: Path) -> bool:
    return path.suffix.lower() == ".log" and any(name in path.parts for name in _LOG_DIRS)


def _state_path(session: str, agent: str) -> str:
    safe = "".join(c for c in f"{session}-{agent}" if c.isalnum() or c in "-_")[:96] or "unknown"
    return os.path.join(_STATE_DIR, f"read-redirect-{safe}.json")


def _told(state: str) -> list[str]:
    try:
        with open(state, encoding="utf-8") as handle:
            told = json.load(handle)
    except (OSError, ValueError):
        return []
    return [str(entry) for entry in told] if isinstance(told, list) else []


def _was_told(state: str, path: Path) -> bool:
    return str(path) in _told(state)


def _mark_told(state: str, path: Path) -> None:
    """Record that the agent was refused a whole read of ``path``: its repeat is let through."""
    told = [*_told(state), str(path)]  # read before the file is opened for writing, which empties it
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(state, "w", encoding="utf-8") as handle:
            json.dump(told, handle)
    except OSError as exc:
        sys.stderr.write(f"redirect-large-read: could not record the notice in {state}: {exc}\n")


def _outline_text(workspace: Path, relative: str) -> str:
    """The file's outline from the code index, refreshed first; empty when the index has no such file."""
    if LIBRARY_DIR not in sys.path:
        sys.path.insert(0, LIBRARY_DIR)
    from code_index.queries import QueryError, outline
    from code_index.session import open_session
    from code_index.sources import CodeIndexError

    try:
        session = open_session(workspace)
    except CodeIndexError:
        return ""
    try:
        session.refresh()
        text = outline(session.conn, relative).render()
    except (QueryError, CodeIndexError):
        return ""
    finally:
        session.close()
    lines = text.splitlines()
    clipped = "\n".join(lines[:MAX_OUTLINE_LINES])[:MAX_OUTLINE_CHARS]
    if len(clipped.splitlines()) < len(lines):
        clipped += (f"\n... {len(lines) - len(clipped.splitlines())} more outline lines: ask the outline tool for "
                    f"the rest, or read the ranges above.")
    return clipped


def _tool_notes(directory: str) -> str:
    notes: list[str] = []
    if is_registered(directory, CODE_INDEX_SERVER):
        notes.append("mcp__datrix-code-index__find_symbol / find_references locate a definition or its uses")
    if is_registered(directory, LOCAL_LLM_SERVER):
        notes.append("mcp__datrix-local-llm__ask_files answers a question about this file from a local model, "
                     "citing path:line, without the text entering your context")
    return "".join(f"\n  - {note}" for note in notes)


def _python_message(label: str, size: int, outline: str, directory: str) -> str:
    return (
        f"READ REDIRECTED: {label} is {size:,} bytes (about {size // CHARS_PER_TOKEN:,} tokens), and a whole read "
        f"costs that every time. Its outline, from the code index as the file stands now:\n\n{outline}\n\n"
        f"Read only what you need: Read with offset and limit on the line ranges above.{_tool_notes(directory)}\n"
        f"If you do need the whole file (to rewrite it, say), repeat the same Read: this notice is shown once "
        f"per file per agent."
    )


def _log_message(label: str, size: int, digest: str) -> str:
    return (
        f"READ REDIRECTED: {label} is {size:,} bytes (about {size // CHARS_PER_TOKEN:,} tokens). A local model read "
        f"it for you:\n\n{digest}\n\nRead the cited line ranges (offset and limit) for detail. If you do need the "
        f"whole log, repeat the same Read: this notice is shown once per file per agent."
    )


def decide(payload: dict[str, object], workspace: Path, settings: "LocalLlmSettings",
           on_repeat: Callable[[], None] | None = None) -> str:
    """The refusal message for this Read, or the empty string to let it through.

    ``on_repeat`` is called when the read is the repeat of one already refused: the agent went
    on to read the whole file after all."""
    tool_input = payload.get("tool_input")
    if str(payload.get("tool_name", "")) != "Read" or not isinstance(tool_input, dict):
        return ""
    if any(key in tool_input for key in ("offset", "limit", "pages")):
        return ""
    raw = str(tool_input.get("file_path", ""))
    if not raw:
        return ""
    if LIBRARY_DIR not in sys.path:
        sys.path.insert(0, LIBRARY_DIR)
    from shared.local_reading import ReadScope, ReadScopeError

    scope = ReadScope(workspace)
    try:
        path = scope.files([raw])[0]
    except ReadScopeError:
        return ""
    kind = "python" if path.suffix == ".py" else "log" if _is_log(path) else ""
    size = path.stat().st_size
    if not kind or size < (LARGE_PY_BYTES if kind == "python" else LARGE_LOG_BYTES):
        return ""
    state = _state_path(str(payload.get("session_id", "")), str(payload.get("agent_id", "")) or "main")
    if _was_told(state, path):
        if on_repeat is not None:
            on_repeat()
        return ""
    label = scope.label(path)
    if kind == "python":
        outline = _outline_text(workspace, label)
        message = _python_message(label, size, outline, session_directory(str(payload.get("cwd", "")))) \
            if outline else ""
    else:
        digest = digest_of(path, workspace, settings, "redirect-large-read")
        message = _log_message(label, size, digest) if digest else ""
    if message:
        _mark_told(state, path)
    return message


def _record(payload: dict[str, object], category: str, response_chars: int) -> None:
    tool_input = payload.get("tool_input")
    detail = str(tool_input.get("file_path", "")) if isinstance(tool_input, dict) else ""
    append_record(_USAGE_LOG, {
        "category": category, "tool": "Read", "detail": detail[:300], "response_chars": response_chars,
        "session": str(payload.get("session_id", "")), "agent": str(payload.get("agent_id", "")) or "main",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }, "redirect-large-read", _USAGE_LOG_MAX_BYTES)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    try:
        if LIBRARY_DIR not in sys.path:
            sys.path.insert(0, LIBRARY_DIR)
        from shared.venv import get_datrix_root

        message = decide(payload, get_datrix_root(), default_settings(CALLER),
                         on_repeat=lambda: _record(payload, REPEAT_CATEGORY, 0))
    except Exception as exc:  # a hook must never fail the tool call it observed
        sys.stderr.write(f"redirect-large-read: skipped: {type(exc).__name__}: {exc}\n")
        sys.exit(0)
    if not message:
        sys.exit(0)
    _record(payload, REDIRECT_CATEGORY, len(message))
    sys.stderr.write(message + "\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
