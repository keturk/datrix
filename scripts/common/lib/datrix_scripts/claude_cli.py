"""What every script that runs the Claude Code CLI shares: its name on ``PATH`` and the batch-shim refusal.

On Windows ``claude`` on ``PATH`` is ``claude.cmd``, a batch shim that ``cmd.exe`` runs and parses: a
line break in an argument ends the command there (the rest of the argument and every argument after it
never reach the CLI), and ``&``, ``|``, ``<``, ``>``, ``^``, ``%``, ``!``, ``"`` and parentheses are
read as ``cmd.exe`` syntax. So a script hands the CLI its prompt on stdin, never as an argument, and
``require_batch_safe`` refuses any remaining argument holding one of those characters before the launch,
rather than letting ``cmd.exe`` run something else.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import UsageError

CLAUDE: Final = "claude"
BATCH_SHIM_SUFFIXES: Final = frozenset({".bat", ".cmd"})
CMD_METACHARACTERS: Final = frozenset('&|<>^%!"()\r\n')


def batch_unsafe_arguments(command: Sequence[str]) -> list[str]:
    """The arguments of *command* that ``cmd.exe`` would parse, when its executable is a batch shim; else none."""
    if Path(command[0]).suffix.lower() not in BATCH_SHIM_SUFFIXES:
        return []
    return [argument for argument in command[1:] if CMD_METACHARACTERS & set(argument)]


def require_batch_safe(command: Sequence[str], fix: str) -> None:
    """Refuse *command* when it runs a batch shim (``claude.cmd``) with an argument ``cmd.exe`` would parse.

    Raises:
        UsageError: naming the arguments, the characters and *fix* (what the caller should pass instead).
    """
    unsafe = batch_unsafe_arguments(command)
    if unsafe:
        raise UsageError(
            f"{command[0]} is a batch shim that cmd.exe runs, and these arguments hold a cmd.exe metacharacter "
            f"({''.join(sorted(CMD_METACHARACTERS - {chr(13), chr(10)}))} or a line break): {unsafe}. Fix: {fix}"
        )
