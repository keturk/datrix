"""PreToolUse hook: hard-block the commands CLAUDE.md forbids outright.

Two families live here, because both were prose rules that were ignored until the
harness enforced them.

FAMILY 1 -- git operations that revert or discard working-tree changes.
The agent cannot know how many prior tasks have modified working-tree files, so a
revert may destroy uncommitted work that is not its own.

Blocked:
  git restore ...            git stash ...          git revert ...
  git reset ...              git clean -f/-fd/-x    git checkout <path>/<ref>/./--
  git checkout -f/--force

Allowed (these create, they do not discard):
  git checkout -b <name>     git switch -c <name>   git checkout --orphan
  git stash list             git reflog             git status/diff/log/show

The one exemption -- `/resolve-conflicts`. Pulling over uncommitted work needs a few
of the shapes above, so while the most recent HUMAN prompt in the transcript is
Jon's own `/resolve-conflicts` invocation, and only then, these become allowed:

  git stash push [...] -- <paths>   shelve exactly the files the pull would overwrite
  git stash pop|apply|drop|show     bring them back / drop the entry once reapplied
  git checkout --ours|--theirs ...  pick a side of a conflicted path mid-merge
  git reset [-q] [HEAD] [-- <paths>] unstage (mixed, index only -- the tree is kept)
  git restore --staged <paths>      unstage, never touching the working tree

Everything that destroys work stays blocked even then: `reset --hard/--keep/--soft`
or to another commit, `restore` of the working tree, `checkout -- <path>`, a bare
or path-less `stash`/`stash clear`, `revert`, and `clean -f`.

The exemption is read from the transcript the harness writes, never from a state
file an agent could author: a user entry that is neither a tool result nor harness
meta text is a prompt Jon typed. The skill is `disable-model-invocation`, so no
agent can open the window itself. An unreadable transcript grants nothing -- fail
closed. A follow-up prompt closes the window, like any other skill scoping.

FAMILY 2 -- standalone type-checkers.
CLAUDE.md, "Running Python": "Never run a standalone type-checker -- no agent,
skill, or gate invokes `mypy` or any equivalent. Write fully type-hinted code;
the tests of the code you changed are the gate."

That rule was written in five documents and enforced by none of them. On
2026-09-03 an agent asked for a workspace type-check ran `.venv/Scripts/mypy.exe`
directly, 33 tool calls, cd-ing into each of the 15 installable package roots.
mypy writes `.mypy_cache/` into its WORKING DIRECTORY, so the run left ~51,400
cache files (~1 GB) inside 15 separate git repositories and turned the
repo-level ignored-source gate red. The wrapper script was never involved.

`datrix/scripts/test/mypy.ps1` deliberately survives: it is the human path (its
only caller is affected-gate.ps1's opt-in -Mypy switch) and it now writes its
cache outside every repo. A person running it in his own terminal is not a tool
call and never reaches this hook. An agent running it is exactly what the rule
forbids -- so the binaries, the `-m` form, and the wrappers are all blocked here.

Reading any of these scripts is never blocked: read-only segments are dropped
before the command is inspected.

Exit codes:
  0 — allow
  2 — block (stderr becomes feedback to Claude)
"""

import functools
import json
import os
import re
import shlex
import sys
from typing import Any, Final

from _command_shape import executable_text, leading_token, segments

# Subcommands that always discard or rewrite working-tree / history state.
_ALWAYS_BLOCKED = {
    "restore": "git restore",
    "revert": "git revert",
    "reset": "git reset",
}

# `git stash` is blocked except for read-only inspection subcommands.
_STASH_READONLY = ("list", "show")

# `git clean` is only dangerous with a force/remove flag.
_CLEAN_DANGEROUS_RE = re.compile(r"\bgit\s+clean\b[^\n;|&]*\s-\w*[fdx]")

# `git checkout` is allowed ONLY for branch creation.
_CHECKOUT_SAFE_RE = re.compile(r"\bgit\s+checkout\s+(-b\b|-B\b|--orphan\b)")

# Global git flags may precede the subcommand. Flags that TAKE AN ARGUMENT must be
# listed first — regex alternation is ordered, and a generic `-[^\s]+` branch would
# otherwise consume `-C` while leaving its path argument to be misread as the
# subcommand (so `git -C <dir> reset --hard` would parse as subcommand "<dir>").
_GIT_SUBCOMMAND_RE = re.compile(
    r"\bgit\s+(?:"
    r"-C\s+\S+\s+"
    r"|-c\s+\S+\s+"
    r"|--git-dir(?:=\S+|\s+\S+)\s*"
    r"|--work-tree(?:=\S+|\s+\S+)\s*"
    r"|--exec-path(?:=\S+|\s+\S+)\s*"
    r"|--[^\s]+(?:=\S+)?\s+"
    r"|-[^\s]+\s+"
    r")*([a-z-]+)"
)

_GIT_TAIL = (
    "\n\nCLAUDE.md: 'No git reverts.' You do not know how many prior tasks have "
    "modified working-tree files — reverting may destroy uncommitted work that is "
    "not yours.\n\n"
    "If your own edit was wrong, UNDO IT MANUALLY with Edit/Write. If you are trying "
    "to escape a fix that went sideways, that is not an option either: read the error "
    "text, re-diagnose, and fix the root cause "
    "(.claude/skills/_shared/execution-contract.md).\n\n"
    "Pulling over uncommitted work is Jon's `/resolve-conflicts` (he types it). While "
    "it is the latest prompt it allows path-limited `git stash push -- <paths>`, "
    "`stash pop/apply/drop`, index-only `git reset [HEAD] -- <paths>`, "
    "`git restore --staged`, and `git checkout --ours/--theirs` -- nothing that "
    "discards work."
)

# --- the /resolve-conflicts exemption ---------------------------------------------

#: Jon's typed invocation, as the harness records it at the head of the prompt.
_RESOLVE_CONFLICTS_INVOCATION_RE: Final = re.compile(
    r"^\s*(?:<command-message>[^<]*</command-message>\s*)?"
    r"<command-name>/resolve-conflicts</command-name>"
)

#: How much of the transcript tail is searched for the latest human prompt. A
#: prompt older than this grants nothing -- fail closed.
_TRANSCRIPT_TAIL_BYTES: Final = 8 * 1024 * 1024

#: Where one git call's arguments end inside a compound command.
_CALL_END_RE: Final = re.compile(r"[;|&\n]")

_QUIET_FLAGS: Final = frozenset({"-q", "--quiet"})
_STASH_RESTORING: Final = frozenset({"pop", "apply", "drop", "show", "list"})
_CHECKOUT_SIDES: Final = frozenset({"--ours", "--theirs"})
_RESTORE_STAGED: Final = frozenset({"--staged", "-S"})


def _is_human_prompt(entry: dict[str, Any]) -> bool:
    """A user entry Jon typed: not harness meta text, not a tool result."""
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    content = entry.get("message", {}).get("content", "")
    if isinstance(content, str):
        return True
    return not any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    )


def _prompt_text(entry: dict[str, Any]) -> str:
    content = entry.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


@functools.lru_cache(maxsize=1)
def _resolve_conflicts_active(transcript_path: str) -> bool:
    """True only while the latest human prompt is Jon's `/resolve-conflicts`."""
    if not transcript_path:
        return False
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as handle:
            handle.seek(max(0, size - _TRANSCRIPT_TAIL_BYTES))
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return False

    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and _is_human_prompt(entry):
            return bool(_RESOLVE_CONFLICTS_INVOCATION_RE.match(_prompt_text(entry)))
    return False


def _call_args(normalized: str, match: re.Match[str]) -> list[str]:
    """The arguments of ONE git call, stopping at the next command separator."""
    tail = normalized[match.end() :]
    end = _CALL_END_RE.search(tail)
    call = tail[: end.start()] if end else tail
    try:
        return shlex.split(call)
    except ValueError:
        return call.split()


def _has_paths_after_separator(args: list[str]) -> bool:
    return "--" in args and args.index("--") < len(args) - 1


def _stash_resolvable(args: list[str]) -> bool:
    """Restoring a stash, or shelving an explicit path list -- never everything."""
    if not args:
        return False
    if args[0] in _STASH_RESTORING:
        return True
    return args[0] == "push" and _has_paths_after_separator(args)


def _checkout_resolvable(args: list[str]) -> bool:
    """`--ours`/`--theirs` on named paths: picks a side of a conflict, drops no work."""
    return bool(args) and args[0] in _CHECKOUT_SIDES and _has_paths_after_separator(args)


def _reset_resolvable(args: list[str]) -> bool:
    """An index-only (mixed) reset to HEAD: unstages, keeps the tree and the branch."""
    rest = [arg for arg in args if arg not in _QUIET_FLAGS]
    if rest and rest[0] == "HEAD":
        rest = rest[1:]
    return not rest or (rest[0] == "--" and len(rest) > 1)


def _restore_resolvable(args: list[str]) -> bool:
    """`restore --staged` alone: the index changes, the working tree never does."""
    before_separator = args[: args.index("--")] if "--" in args else args
    flags = [arg for arg in before_separator if arg.startswith("-")]
    return bool(set(flags) & _RESTORE_STAGED) and set(flags) <= (
        _RESTORE_STAGED | _QUIET_FLAGS
    )


_RESOLVABLE: Final = {
    "stash": _stash_resolvable,
    "checkout": _checkout_resolvable,
    "reset": _reset_resolvable,
    "restore": _restore_resolvable,
}


def _exempt(subcommand: str, args: list[str], transcript_path: str) -> bool:
    """The shape is one the skill needs AND Jon's invocation is the live prompt.

    The transcript is read only for a shape that could be exempt, so an ordinary
    blocked command costs no file read.
    """
    predicate = _RESOLVABLE.get(subcommand)
    if predicate is None or not predicate(args):
        return False
    return _resolve_conflicts_active(transcript_path)

# Executable names that ARE a standalone type-checker. `leading_token` returns the
# bare basename with any `.exe` stripped, so an absolute venv path matches too.
_TYPE_CHECKERS = frozenset({"mypy", "dmypy", "pyright", "pyre", "pytype"})

# Interpreters that reach a type-checker through `-m`.
_PY_LAUNCHERS = frozenset({"python", "python3", "py", "pythonw"})

# Shells and script hosts that reach a wrapper script through an argument.
_EXECUTORS = frozenset({"powershell", "pwsh", "cmd", "bash", "sh", "zsh", "start"})

_MODULE_FORM_RE = re.compile(
    r"(?<![\w.-])-m\s+(" + "|".join(sorted(_TYPE_CHECKERS)) + r")\b", re.IGNORECASE
)

# The repo's own type-check entry points. Bounded on the left so `check_mypy.py`
# and `run-mypy.ps1` are not read as these files.
_WRAPPER_RE = re.compile(r"(?<![\w.-])mypy\.(?:ps1|py)\b", re.IGNORECASE)

# affected-gate.ps1 only type-checks when its opt-in switch is passed.
_AFFECTED_GATE_RE = re.compile(r"(?<![\w.-])affected-gate\.ps1\b", re.IGNORECASE)
_MYPY_SWITCH_RE = re.compile(r"(?<![\w.-])-{1,2}mypy\b", re.IGNORECASE)

_TYPE_CHECKER_TAIL = (
    "\n\nCLAUDE.md, 'Running Python': 'Never run a standalone type-checker — no "
    "agent, skill, or gate invokes `mypy` or any equivalent. Write fully "
    "type-hinted code; the tests of the code you changed are the gate.'\n\n"
    "Two reasons, both load-bearing:\n"
    "  * Type correctness is already gated by the tests of the code you changed. A separate "
    "type-check is not your verification step and only burns tokens and turns.\n"
    "  * mypy writes `.mypy_cache/` into its WORKING DIRECTORY. Run from a package "
    "root it drops the cache inside that git repository — 15 such runs once left "
    "~51,400 files (~1 GB) across 15 repos and failed the ignored-source gate.\n\n"
    "A full type-check is a HUMAN-only tool: `.\\scripts\\test\\mypy.ps1 <project>` "
    "(or `-All`), run by Jon in his own terminal. If he asked you for one, say that "
    "in one line and hand him the command — do not run it, and do not route around "
    "this guard."
)


def _block(msg: str, tail: str = _GIT_TAIL) -> None:
    sys.stderr.write(msg + tail)
    sys.exit(2)


def _check_command(command: str, transcript_path: str) -> None:
    """Block the command if it contains a working-tree-destroying git call."""
    normalized = " ".join(command.split())

    for match in _GIT_SUBCOMMAND_RE.finditer(normalized):
        subcommand = match.group(1)

        if _exempt(subcommand, _call_args(normalized, match), transcript_path):
            continue

        if subcommand in _ALWAYS_BLOCKED:
            _block(f"BLOCKED: `{_ALWAYS_BLOCKED[subcommand]}` discards changes.")

        if subcommand == "stash":
            tail = normalized[match.end() :].lstrip()
            first_arg = tail.split()[0] if tail.split() else ""
            if first_arg not in _STASH_READONLY:
                _block("BLOCKED: `git stash` shelves changes that may not be yours.")

        if subcommand == "checkout":
            checkout_call = normalized[match.start() :]
            if not _CHECKOUT_SAFE_RE.match(checkout_call):
                _block(
                    "BLOCKED: `git checkout` of a path or ref discards working-tree "
                    "changes. (Only `git checkout -b` / `--orphan` is allowed — those "
                    "create a branch rather than discarding work.)"
                )

    if _CLEAN_DANGEROUS_RE.search(normalized):
        _block("BLOCKED: `git clean -f/-d/-x` deletes untracked files.")


def _script_argument(segment: str) -> str:
    """The first non-flag argument after the executable -- the script it runs.

    Naming a script is not running one. `python -m py_compile <path>` runs
    py_compile; `-m` consumes the module name, so the first non-flag token is
    `py_compile` and the path that follows is data. That distinction is what
    keeps a syntax check, or any scripted inspection of a guarded file, from
    reading as an invocation of it -- the exact over-block `_command_shape`
    exists to prevent.
    """
    try:
        tokens = shlex.split(segment, posix=False)
    except ValueError:
        tokens = segment.split()
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        return token
    return ""


def _script_run_by(segment: str, token: str) -> str:
    """The script this segment EXECUTES, or "" when it executes none.

    A wrapper is run either directly (`& ...\\mypy.ps1`) or as the script
    argument of an interpreter or shell host (`powershell -File ...`).
    """
    if token.endswith((".ps1", ".py")):
        return token
    if token in _EXECUTORS or token in _PY_LAUNCHERS:
        return _script_argument(segment)
    return ""


def _check_type_checker(command: str) -> None:
    """Block a segment that RUNS a standalone type-checker.

    Only executing segments are examined -- `grep mypy scripts/test/mypy.ps1` and
    `Remove-Item -Recurse .mypy_cache` must stay possible, and the second one
    especially: cleaning up after this defect must never be blocked by the guard
    that objects to it.
    """
    for segment in segments(executable_text(command)):
        token = leading_token(segment)

        if token in _TYPE_CHECKERS:
            _block(
                f"BLOCKED: `{token}` is a standalone type-checker.", _TYPE_CHECKER_TAIL
            )

        if token in _PY_LAUNCHERS:
            match = _MODULE_FORM_RE.search(segment)
            if match:
                _block(
                    f"BLOCKED: `-m {match.group(1)}` runs a standalone type-checker.",
                    _TYPE_CHECKER_TAIL,
                )

        script = _script_run_by(segment, token)
        if not script:
            continue

        if _WRAPPER_RE.search(script):
            _block(
                "BLOCKED: `mypy.ps1` / `mypy.py` runs a standalone type-checker.",
                _TYPE_CHECKER_TAIL,
            )

        if _AFFECTED_GATE_RE.search(script) and _MYPY_SWITCH_RE.search(segment):
            _block(
                "BLOCKED: `affected-gate.ps1 -Mypy` type-checks the changed packages.",
                _TYPE_CHECKER_TAIL,
            )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if command:
        _check_command(command, data.get("transcript_path") or "")
        _check_type_checker(command)

    sys.exit(0)


if __name__ == "__main__":
    main()
