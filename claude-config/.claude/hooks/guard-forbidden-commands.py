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

FAMILY 2 -- standalone type-checkers.
CLAUDE.md, "Running Python": "Never run a standalone type-checker -- no agent,
skill, or gate invokes `mypy` or any equivalent. Write fully type-hinted code;
the package suites are the gate."

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

import json
import re
import shlex
import sys

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
    "(.claude/skills/_shared/execution-contract.md)."
)

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
    "type-hinted code; the package suites are the gate.'\n\n"
    "Two reasons, both load-bearing:\n"
    "  * Type correctness is already gated by the package suites. A separate "
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


def _check_command(command: str) -> None:
    """Block the command if it contains a working-tree-destroying git call."""
    normalized = " ".join(command.split())

    for match in _GIT_SUBCOMMAND_RE.finditer(normalized):
        subcommand = match.group(1)

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
        _check_command(command)
        _check_type_checker(command)

    sys.exit(0)


if __name__ == "__main__":
    main()
