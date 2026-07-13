"""PreToolUse hook: hard-block git operations that revert or discard working-tree changes.

CLAUDE.md forbids these outright: the agent cannot know how many prior tasks have
modified working-tree files, so a revert may destroy uncommitted work. This was a
prose rule and was ignored. It is now enforced by the harness.

Blocked:
  git restore ...            git stash ...          git revert ...
  git reset ...              git clean -f/-fd/-x    git checkout <path>/<ref>/./--
  git checkout -f/--force

Allowed (these create, they do not discard):
  git checkout -b <name>     git switch -c <name>   git checkout --orphan
  git stash list             git reflog             git status/diff/log/show

Exit codes:
  0 — allow
  2 — block (stderr becomes feedback to Claude)
"""

import json
import re
import sys

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

_MESSAGE_TAIL = (
    "\n\nCLAUDE.md: 'No git reverts.' You do not know how many prior tasks have "
    "modified working-tree files — reverting may destroy uncommitted work that is "
    "not yours.\n\n"
    "If your own edit was wrong, UNDO IT MANUALLY with Edit/Write. If you are trying "
    "to escape a fix that went sideways, that is not an option either: read the error "
    "text, re-diagnose, and fix the root cause "
    "(.claude/skills/_shared/execution-contract.md)."
)


def _block(msg: str) -> None:
    sys.stderr.write(msg + _MESSAGE_TAIL)
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


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if command:
        _check_command(command)

    sys.exit(0)


if __name__ == "__main__":
    main()
